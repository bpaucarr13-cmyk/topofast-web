import os

os.environ.setdefault("GDAL_BIN_DIR", r"C:\Program Files\QGIS 4.2.2\bin")
os.environ.setdefault("GDAL_DATA_DIR", r"C:\Program Files\QGIS 4.2.2\apps\gdal\share\gdal")
os.environ.setdefault("PROJ_LIB_DIR", r"C:\Program Files\QGIS 4.2.2\share\proj")
os.environ.setdefault("GDAL_PYTHON", r"C:\Program Files\QGIS 4.2.2\apps\Python312\python.exe")

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
