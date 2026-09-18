import os
import shutil
import tempfile
import time
import uuid

# Carpeta raíz donde vive cada job (una subcarpeta por pedido). Separada del
# temp del sistema para poder limpiarla entera sin tocar nada de otro
# proceso, y para poder listarla y borrar jobs viejos por antigüedad.
JOBS_ROOT = os.path.join(tempfile.gettempdir(), "topofast_web_jobs")

# Un área más grande que esto tarda demasiado y puede colgar un request
# público; OpenTopography igual tiene sus propios límites por tipo de DEM,
# pero conviene rechazar antes de gastar tiempo de servidor y cupo de API.
MAX_AREA_DEG2 = 4.0  # ~ 440km x 440km en el ecuador, de sobra para uso real

JOB_TTL_SECONDS = 3600  # una hora: tiempo de sobra para que el usuario baje los resultados


def new_job_dir() -> tuple[str, str]:
    os.makedirs(JOBS_ROOT, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(JOBS_ROOT, job_id)
    os.makedirs(job_dir, exist_ok=True)
    return job_id, job_dir


def job_dir_for(job_id: str) -> str:
    # Se valida que job_id sea un hex simple (viene de new_job_dir) antes de
    # unirlo a una ruta, para no permitir path traversal desde el cliente.
    if not job_id.isalnum() or len(job_id) > 40:
        raise ValueError("job_id inválido")
    return os.path.join(JOBS_ROOT, job_id)


def check_area_size(min_lon, min_lat, max_lon, max_lat):
    width = max_lon - min_lon
    height = max_lat - min_lat
    if width <= 0 or height <= 0:
        raise ValueError("El área seleccionada no es válida.")
    if width * height > MAX_AREA_DEG2:
        raise ValueError(
            "El área seleccionada es demasiado grande para procesarla acá. "
            "Probá con un área más chica."
        )


def cleanup_old_jobs(ttl_seconds: int = JOB_TTL_SECONDS):
    if not os.path.isdir(JOBS_ROOT):
        return
    now = time.time()
    for name in os.listdir(JOBS_ROOT):
        path = os.path.join(JOBS_ROOT, name)
        try:
            if now - os.path.getmtime(path) > ttl_seconds:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
