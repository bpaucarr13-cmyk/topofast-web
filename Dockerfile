# Imagen oficial de GDAL: ya trae gdal_translate, gdal_contour, gdalwarp,
# ogr2ogr, gdaldem y gdal_fillnodata.py en el PATH, con GDAL_DATA/PROJ_LIB
# configurados correctamente — evita el problema que apareció en desarrollo
# en Windows (GDAL_DATA is not defined) al llamar estas herramientas fuera
# del entorno de QGIS.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.9.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
