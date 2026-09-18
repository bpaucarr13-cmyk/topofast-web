import datetime
import os

import numpy as np
import rasterio

NODATA_VALUE = -9999.0


def build_landxml(utm_dem_path, out_path):
    # Misma idea que _export_landxml en el plugin (TIN ya triangulado a
    # partir de la grilla del DEM, 2 triángulos por celda 2x2 de píxeles
    # válidos, convención Norte-Este-Elevación), pero leyendo la grilla con
    # rasterio/NumPy en vez de QgsRasterBlock, y escribiendo el XML directo
    # al archivo (no en listas gigantes en memoria) para que aguante DEMs
    # grandes sin usar cientos de MB de RAM.
    with rasterio.open(utm_dem_path) as ds:
        band = ds.read(1).astype("float64")
        nodata = ds.nodata if ds.nodata is not None else NODATA_VALUE
        transform = ds.transform
        height, width = band.shape

    valid = band != nodata

    rows = np.arange(height)
    cols = np.arange(width)
    col_grid, row_grid = np.meshgrid(cols, rows)
    # Centro de cada píxel: transform ya ubica la esquina superior-izq;
    # sumar 0.5 pasa al centro de la celda.
    xs = transform.c + (col_grid + 0.5) * transform.a + (row_grid + 0.5) * transform.b
    ys = transform.f + (col_grid + 0.5) * transform.d + (row_grid + 0.5) * transform.e

    point_ids = np.full((height, width), -1, dtype=np.int64)
    point_ids[valid] = np.arange(1, valid.sum() + 1)

    timestamp = datetime.datetime.now()

    point_count = 0
    face_count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.2" version="1.2" '
            f'date="{timestamp:%Y-%m-%d}" time="{timestamp:%H:%M:%S}">\n'
            '  <Units>\n'
            '    <Metric areaUnit="squareMeter" linearUnit="meter" volumeUnit="cubicMeter" '
            'temperatureUnit="celsius" pressureUnit="mmHG"/>\n'
            '  </Units>\n'
            '  <Surfaces>\n'
            '    <Surface name="TopoFast">\n'
            '      <Definition surfType="TIN">\n'
            '        <Pnts>\n'
        )
        for row in range(height):
            for col in range(width):
                pid = point_ids[row, col]
                if pid < 0:
                    continue
                f.write(
                    f'          <P id="{pid}">{ys[row, col]:.3f} '
                    f'{xs[row, col]:.3f} {band[row, col]:.3f}</P>\n'
                )
                point_count += 1

        f.write('        </Pnts>\n        <Faces>\n')
        for row in range(height - 1):
            for col in range(width - 1):
                top_left = point_ids[row, col]
                top_right = point_ids[row, col + 1]
                bottom_left = point_ids[row + 1, col]
                bottom_right = point_ids[row + 1, col + 1]
                if min(top_left, top_right, bottom_left, bottom_right) < 0:
                    continue
                f.write(f"          <F>{top_left} {bottom_left} {bottom_right}</F>\n")
                f.write(f"          <F>{top_left} {bottom_right} {top_right}</F>\n")
                face_count += 1

        f.write(
            '        </Faces>\n'
            '      </Definition>\n'
            '    </Surface>\n'
            '  </Surfaces>\n'
            '</LandXML>\n'
        )

    if point_count == 0 or face_count == 0:
        os.remove(out_path)
        raise ValueError("No hay suficientes datos válidos para armar la superficie TIN.")

    return out_path
