import time
import threading
from collections import defaultdict

from fastapi import HTTPException, Request

# Rate limit simple en memoria (sin Redis ni base de datos, a tono con el
# resto de la app): alcanza para una instancia única de tamaño personal. Si
# en algún momento se despliega con varios workers/réplicas, cada uno tendría
# su propio conteo — recién ahí haría falta un backend compartido.
_WINDOW_SECONDS = 600
_MAX_REQUESTS = 20

_lock = threading.Lock()
_hits = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request):
    ip = _client_ip(request)
    now = time.time()
    with _lock:
        recent = [t for t in _hits[ip] if now - t < _WINDOW_SECONDS]
        if len(recent) >= _MAX_REQUESTS:
            raise HTTPException(
                429,
                f"Demasiados pedidos desde tu conexión. Esperá unos minutos "
                f"(límite: {_MAX_REQUESTS} cada {_WINDOW_SECONDS // 60} min).",
            )
        recent.append(now)
        _hits[ip] = recent
