# Imagen oficial de GDAL: ya trae gdal_translate, gdal_contour, gdalwarp,
# ogr2ogr, gdaldem y gdal_fillnodata.py en el PATH, con GDAL_DATA/PROJ_LIB
# resueltos correctamente — evita el problema que apareció en desarrollo
# en Windows (GDAL_DATA is not defined) al llamar estas herramientas fuera
# del entorno de QGIS.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.9.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Falla temprano y con un mensaje claro si a la imagen le falta alguna
# herramienta que usa processing.py.
RUN which gdal_translate gdal_contour gdalwarp ogr2ogr gdaldem gdal_fillnodata.py

WORKDIR /app

# La app corre en un venv propio: la imagen trae numpy instalado por apt (lo
# usan los scripts de GDAL con el python3 del sistema) y pip no puede
# reemplazarlo ("Cannot uninstall numpy, RECORD file not found"). Con un venv
# sin system-site-packages cada uno tiene sus propias versiones y ninguno pisa
# al otro.
COPY backend/requirements.txt backend/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

# Si gdal_fillnodata.py no estuviera en el PATH, processing.py lo corre con
# "-m osgeo_utils.gdal_fillnodata": ese módulo solo existe en el python3 del
# sistema (donde están los bindings osgeo), no en el venv de la app.
ENV GDAL_PYTHON=/usr/bin/python3

EXPOSE 8000
CMD ["/opt/venv/bin/python", "-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
