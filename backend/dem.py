import os
import urllib.request
import urllib.parse
import urllib.error

DOWNLOAD_TIMEOUT_SECONDS = 120
DOWNLOAD_CHUNK_BYTES = 256 * 1024
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # corta una respuesta descontrolada


class DemDownloadError(Exception):
    pass


def download_dem(min_lon, min_lat, max_lon, max_lat, demtype, api_key, dest_path):
    # Mismo endpoint y manejo de errores que el plugin de QGIS
    # (E:\topofast\topofast.py:_download_dem): timeout explícito (antes de
    # esto una respuesta colgada bloqueaba indefinidamente) y detección del
    # mensaje de rate-limit de OpenTopography (50 descargas/24hs) para dar
    # un mensaje claro en vez del texto crudo de la API.
    query = {
        "demtype": demtype,
        "south": min_lat,
        "north": max_lat,
        "west": min_lon,
        "east": max_lon,
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }
    url = "https://portal.opentopography.org/API/globaldem?" + urllib.parse.urlencode(query)

    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            downloaded = 0
            with open(dest_path, "wb") as out_file:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise DemDownloadError("El DEM devuelto es demasiado grande.")
                    out_file.write(chunk)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        if "rate limit" in body.lower():
            raise DemDownloadError(
                "Alcanzaste el límite gratuito de OpenTopography (50 descargas cada "
                "24 horas). Esperá a que se libere cupo y volvé a intentar más tarde."
            ) from exc
        raise DemDownloadError(
            f"OpenTopography respondió con error {exc.code}. "
            f"Revisá la API Key y el área seleccionada.\n{body[:300]}"
        ) from exc
    except TimeoutError as exc:
        raise DemDownloadError(
            "OpenTopography no respondió a tiempo (se agotó el tiempo de espera). "
            "Probá de nuevo en un momento o con un área más chica."
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise DemDownloadError(
                "OpenTopography no respondió a tiempo (se agotó el tiempo de espera)."
            ) from exc
        raise DemDownloadError(f"No se pudo conectar con OpenTopography: {exc.reason}") from exc

    if not os.path.exists(dest_path) or os.path.getsize(dest_path) < 1000:
        raise DemDownloadError("El DEM descargado está vacío o incompleto. Probá con un área más chica.")
