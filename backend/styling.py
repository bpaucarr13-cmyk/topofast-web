import json
import io

import numpy as np
import rasterio
from PIL import Image

NODATA_VALUE = -9999.0

# Mismo degradé verde-amarillo-marrón-blanco que _style_dem en el plugin.
DEM_COLOR_STOPS = [
    (0.0, (40, 90, 40)),
    (0.35, (160, 200, 90)),
    (0.6, (235, 220, 130)),
    (0.8, (180, 120, 80)),
    (1.0, (255, 255, 255)),
]


def classify_master_contours(geojson_path, master_interval):
    # Mismo criterio (con tolerancia de punto flotante) que _style_contours
    # en el plugin: comparar "ELEV % interval == 0" de forma exacta fallaba
    # por errores de redondeo y clasificaba mal curvas maestras de forma
    # intermitente. Acá se agrega la propiedad "master" a cada feature para
    # que el frontend la dibuje gruesa+etiquetada o fina, sin recalcular
    # nada en el navegador.
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for feature in data.get("features", []):
        elev = feature.get("properties", {}).get("ELEV")
        if elev is None:
            feature.setdefault("properties", {})["master"] = False
            continue
        is_master = abs(elev - round(elev / master_interval) * master_interval) < 0.001
        feature["properties"]["master"] = is_master

    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return data


def _lerp_color(c0, c1, t):
    return tuple(c0[i] + (c1[i] - c0[i]) * t for i in range(3))


def _ramp_color(t):
    for (t0, c0), (t1, c1) in zip(DEM_COLOR_STOPS, DEM_COLOR_STOPS[1:]):
        if t0 <= t <= t1:
            local_t = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return _lerp_color(c0, c1, local_t)
    return DEM_COLOR_STOPS[-1][1]


def render_dem_png(dem_path, out_png_path):
    # Devuelve además los bounds en EPSG:4326 para que el frontend pueda
    # ubicar el overlay con L.imageOverlay(url, bounds) en Leaflet.
    with rasterio.open(dem_path) as ds:
        band = ds.read(1).astype("float64")
        nodata = ds.nodata if ds.nodata is not None else NODATA_VALUE
        mask = band == nodata
        bounds = ds.bounds

    valid = band[~mask]
    if valid.size == 0:
        raise ValueError("El DEM no tiene píxeles válidos para dibujar.")
    vmin, vmax = float(valid.min()), float(valid.max())
    span = vmax - vmin if vmax > vmin else 1.0

    norm = np.clip((band - vmin) / span, 0.0, 1.0)
    # Tabla de 256 colores en vez de evaluar la rampa píxel por píxel
    # (mucho más rápido para un DEM de varios millones de píxeles).
    lut = np.array([_ramp_color(i / 255) for i in range(256)], dtype=np.uint8)
    idx = (norm * 255).astype(np.uint8)
    rgb = lut[idx]

    alpha = np.where(mask, 0, 255).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])

    Image.fromarray(rgba, mode="RGBA").save(out_png_path, "PNG")

    return {
        "south": bounds.bottom,
        "west": bounds.left,
        "north": bounds.top,
        "east": bounds.right,
    }


def void_fraction(dem_path):
    with rasterio.open(dem_path) as ds:
        band = ds.read(1)
        nodata = ds.nodata if ds.nodata is not None else NODATA_VALUE
        total = band.size
        if total == 0:
            return 0.0
        valid = int((band != nodata).sum())
        return 1.0 - (valid / total)
