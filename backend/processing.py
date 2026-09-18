import os
import shutil
import subprocess
import sys

NODATA_VALUE = -9999.0
FILL_SEARCH_DISTANCE = 100

# En el contenedor Docker de producción estas herramientas ya están en el
# PATH y su entorno (GDAL_DATA/PROJ_LIB) ya viene configurado. En desarrollo
# en Windows (esta PC) no hay una instalación de GDAL separada de QGIS, así
# que se puede apuntar GDAL_BIN_DIR/GDAL_DATA_DIR/PROJ_LIB_DIR a las carpetas
# correspondientes dentro de la instalación de QGIS. Sin GDAL_DATA, por
# ejemplo, el driver DXF de ogr2ogr no encuentra su plantilla header.dxf y
# falla con "GDAL_DATA is not defined".
GDAL_BIN_DIR = os.environ.get("GDAL_BIN_DIR", "")
GDAL_DATA_DIR = os.environ.get("GDAL_DATA_DIR", "")
PROJ_LIB_DIR = os.environ.get("PROJ_LIB_DIR", "")
GDAL_PYTHON = os.environ.get("GDAL_PYTHON", sys.executable)

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class GdalError(Exception):
    pass


def _find_tool(name):
    exe = name + ".exe" if os.name == "nt" else name
    found = shutil.which(name) or shutil.which(exe)
    if found:
        return found
    if GDAL_BIN_DIR:
        candidate = os.path.join(GDAL_BIN_DIR, exe)
        if os.path.exists(candidate):
            return candidate
    raise GdalError(f"No se encontró la herramienta GDAL '{name}' (ver GDAL_BIN_DIR).")


def _subprocess_env():
    env = os.environ.copy()
    if GDAL_DATA_DIR:
        env["GDAL_DATA"] = GDAL_DATA_DIR
    if PROJ_LIB_DIR:
        env["PROJ_LIB"] = PROJ_LIB_DIR
    return env


def _run(cmd):
    result = subprocess.run(
        cmd, capture_output=True, text=True, creationflags=_CREATIONFLAGS, env=_subprocess_env()
    )
    if result.returncode != 0:
        raise GdalError(f"Falló '{cmd[0]}': {result.stderr.strip() or result.stdout.strip()}")
    return result


def tag_nodata(src_path, dst_path):
    # Reetiqueta el valor de vacíos (-9999) como NoData real, igual que
    # gdal:translate en el plugin — si no, el color del ráster y las curvas
    # de nivel tratan los vacíos de glaciar/nieve como datos válidos.
    tool = _find_tool("gdal_translate")
    _run([tool, "-a_nodata", str(NODATA_VALUE), src_path, dst_path])


def fill_nodata(src_path, dst_path):
    # gdal_fillnodata.py es un script Python (usa los bindings osgeo), no un
    # binario — se busca primero como ejecutable directo (así viene en la
    # imagen Docker de GDAL), y si no está en el PATH se lo corre con
    # "-m osgeo_utils.gdal_fillnodata" usando el intérprete configurado
    # (funciona con el Python de QGIS en desarrollo local en Windows).
    direct = shutil.which("gdal_fillnodata.py") or shutil.which("gdal_fillnodata")
    if direct:
        cmd = [direct, "-md", str(FILL_SEARCH_DISTANCE), "-si", "0", src_path, dst_path]
    else:
        cmd = [
            GDAL_PYTHON, "-m", "osgeo_utils.gdal_fillnodata",
            "-md", str(FILL_SEARCH_DISTANCE), "-si", "0", src_path, dst_path,
        ]
    _run(cmd)


def generate_contours_geojson(src_path, dst_geojson_path, interval):
    # CREATE_3D (-3d) + campo ELEV, igual que gdal:contour en el plugin: la
    # elevación real queda en la geometría, no solo como atributo — de ahí
    # sale tanto el dibujo en el mapa como la entrada para el DXF.
    tool = _find_tool("gdal_contour")
    if os.path.exists(dst_geojson_path):
        os.remove(dst_geojson_path)
    _run([
        tool, "-f", "GeoJSON", "-3d", "-a", "ELEV",
        "-i", str(interval), "-snodata", str(NODATA_VALUE),
        src_path, dst_geojson_path,
    ])


def clip_to_polygon(src_path, dst_path, polygon_geojson_path):
    # Recorta al polígono exacto (no al rectángulo/bbox completo), igual que
    # _clip_raster_to_mask en el plugin. gdalwarp puede leer el GeoJSON
    # directo como capa de corte, sin pasar por un shapefile intermedio.
    tool = _find_tool("gdalwarp")
    if os.path.exists(dst_path):
        os.remove(dst_path)
    _run([
        tool, "-cutline", polygon_geojson_path, "-crop_to_cutline",
        "-dstnodata", str(NODATA_VALUE), src_path, dst_path,
    ])


def warp_to_epsg(src_path, dst_path, epsg):
    tool = _find_tool("gdalwarp")
    if os.path.exists(dst_path):
        os.remove(dst_path)
    _run([
        tool, "-t_srs", f"EPSG:{epsg}", "-dstnodata", str(NODATA_VALUE),
        "-r", "near", src_path, dst_path,
    ])


def contours_to_dxf(src_geojson_path, dst_dxf_path, epsg, is_3d):
    # Mismos flags que _export_dxf en el plugin: -skipfailures porque el
    # driver DXF no admite algunos campos de origen, y -dim/-nlt para que
    # OGR no descarte la elevación al pasar a DXF.
    tool = _find_tool("ogr2ogr")
    if os.path.exists(dst_dxf_path):
        os.remove(dst_dxf_path)
    cmd = [tool, "-f", "DXF", "-skipfailures", "-t_srs", f"EPSG:{epsg}"]
    if is_3d:
        cmd += ["-dim", "3", "-nlt", "LINESTRING25D"]
    else:
        cmd += ["-dim", "2"]
    cmd += [dst_dxf_path, src_geojson_path, "contour"]
    _run(cmd)


def slope(src_path, dst_path):
    # SCALE=111120: el DEM está en EPSG:4326 (grados) pero la elevación en
    # metros — sin este factor la pendiente sale ~90° en todos los píxeles
    # (mismo bug ya resuelto en el plugin, ver _build_area_report).
    tool = _find_tool("gdaldem")
    if os.path.exists(dst_path):
        os.remove(dst_path)
    _run([tool, "slope", src_path, dst_path, "-s", "111120"])
