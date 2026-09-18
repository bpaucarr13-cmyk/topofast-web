# TopoFast Web

Versión web standalone de TopoFast: dibujá un área en el navegador, bajá el DEM de [OpenTopography](https://opentopography.org/), extraé curvas de nivel con GDAL, y exportá a DXF/LandXML para CAD — sin instalar QGIS.

## Requisitos

- Python 3.10+ (para correrlo directo) o Docker (para desplegarlo).
- Una **API Key gratuita de OpenTopography** por usuario: se pide en el navegador, se guarda solo ahí (`localStorage`), nunca en el servidor.

## Correrlo localmente (sin Docker)

Necesitás GDAL instalado (herramientas de línea de comandos: `gdal_translate`, `gdal_contour`, `gdalwarp`, `ogr2ogr`, `gdaldem`, `gdal_fillnodata.py`). En Windows, la forma más simple si ya tenés QGIS instalado es reusar su GDAL:

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Configurá las variables de entorno que apuntan a las herramientas de QGIS (ajustá la ruta a tu instalación) y corré el servidor:

```bash
set GDAL_BIN_DIR=C:\Program Files\QGIS 4.2.2\bin
set GDAL_DATA_DIR=C:\Program Files\QGIS 4.2.2\apps\gdal\share\gdal
set PROJ_LIB_DIR=C:\Program Files\QGIS 4.2.2\share\proj
set GDAL_PYTHON=C:\Program Files\QGIS 4.2.2\apps\Python312\python.exe
.venv\Scripts\python run_dev.py
```

(`run_dev.py` ya trae estos valores como default si no están seteados, pensado para esta PC en particular — en otra máquina con QGIS en otra ruta, o con GDAL instalado aparte, ajustá las variables o el default en `run_dev.py`.)

Abrí `http://localhost:8000` en el navegador.

## Correrlo con Docker (recomendado para desplegar)

El `Dockerfile` usa la imagen oficial de GDAL (`ghcr.io/osgeo/gdal`), que ya trae todas las herramientas necesitas con su entorno bien configurado — no hace falta ninguna de las variables de entorno de arriba.

```bash
docker compose up --build
```

Abrí `http://localhost:8000`.

## Subirlo a internet

Cualquier host que soporte Docker sirve. Opciones simples, sin manejar un servidor a mano:

### Railway (recomendado para empezar)

1. Subí este proyecto a un repositorio de GitHub (puede ser privado).
2. Entrá a [railway.app](https://railway.app), creá una cuenta, **"New Project" → "Deploy from GitHub repo"** y elegí el repositorio.
3. Railway detecta el `Dockerfile` solo y lo builda. Al terminar te da una URL pública (`algo.up.railway.app`).
4. No hace falta configurar nada más — no hay secretos del servidor (cada usuario pone su propia API Key en el navegador).

### Render

Muy similar a Railway: **"New" → "Web Service"**, conectás el repo de GitHub, Render detecta el Dockerfile. Tiene un plan gratuito, pero el servicio "duerme" tras un rato sin uso y tarda unos segundos en despertar en el próximo pedido.

### Fly.io

Más control (elegís la región del servidor), se despliega con la CLI `fly launch` parado en esta carpeta (detecta el Dockerfile) y después `fly deploy`.

### Un VPS propio (DigitalOcean, Hetzner, etc.)

Más trabajo (instalar Docker en el servidor, configurar HTTPS con un proxy como Caddy o Nginx), pero sin límites de los planes gratuitos. Recomendable solo si ya tenés experiencia con este tipo de configuración, o si el uso crece mucho.

## Límites y notas de seguridad

- **Sin usuarios ni base de datos**: cada generación es un job aislado en una carpeta temporal (identificada por un id al azar), que se borra sola después de una hora.
- **Límite de área** (`backend/jobs.py`, `MAX_AREA_DEG2`): rechaza áreas gigantes antes de gastar tiempo de servidor.
- **Rate limiting** (`backend/ratelimit.py`): máximo 20 pedidos de generación cada 10 minutos por IP — evita que una sola persona (o un bot) sature el servidor. Es en memoria: si en algún momento se despliega con más de una réplica del servidor, cada una cuenta por separado.
- **Timeout de descarga**: si OpenTopography no responde en 2 minutos, se corta con un mensaje claro en vez de colgar el servidor.
- La **API Key de cada usuario** viaja del navegador a este servidor y de ahí a OpenTopography en cada pedido — nunca se guarda en el servidor ni en logs.

## Estructura del proyecto

```
topofast-web/
├── backend/
│   ├── main.py          # FastAPI: rutas /api/generate, /api/jobs/*, sirve el frontend
│   ├── dem.py             # descarga de OpenTopography (timeout, rate-limit de la API)
│   ├── processing.py       # gdal_translate/fillnodata/contour/warp/ogr2ogr vía subprocess
│   ├── styling.py            # clasificación curva maestra/intermedia, render del DEM a PNG
│   ├── report.py               # estadísticas del área (elevación, pendiente, superficie, zona UTM)
│   ├── landxml.py                # superficie TIN (rasterio + NumPy)
│   ├── jobs.py                     # carpetas temporales por job, límite de área, limpieza
│   ├── ratelimit.py                 # límite de pedidos por IP
│   └── requirements.txt
├── frontend/
│   ├── index.html            # mapa Leaflet + formulario + informe + descargas
│   ├── app.js                  # dibujo del área, llamadas a la API, estilos de curvas
│   └── style.css
├── Dockerfile
├── docker-compose.yml
└── .dockerignore
```
