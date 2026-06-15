from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/ping")
async def ping(current_user: Usuario = Depends(get_current_user)):
    return {"status": "ok", "user_id": current_user.id, "message": "Authenticated"}


# ── Worker lifecycle (dev) ─────────────────────────────────────────

import http.client
import json
import os
import socket
from urllib.parse import quote

_WorkerName = {
    "fast": "gt-worker-fast-1",
    "heavy": "gt-worker-heavy-1",
    "nlp": "gt-worker-nlp-1",
}
_SOCK = "/var/run/docker.sock"


def _docker(action: str, worker: str) -> dict:
    if not os.path.exists(_SOCK):
        return {"ok": False, "error": "Docker socket no disponible"}
    name = _WorkerName.get(worker)
    if not name:
        return {"ok": False, "error": f"Worker desconocido: {worker}"}
    try:
        conn = http.client.HTTPConnection("localhost")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(_SOCK)
        path = f"/v1.41/containers/{quote(name, safe='')}/{action}"
        conn.request("POST", path)
        resp = conn.getresponse()
        conn.close()
        return {"ok": resp.status in (204, 304), "status": resp.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/admin/workers/{worker}/start")
async def start_worker(worker: str, current_user: Usuario = Depends(get_current_user)):
    return _docker("start", worker)


@router.post("/admin/workers/{worker}/stop")
async def stop_worker(worker: str, current_user: Usuario = Depends(get_current_user)):
    return _docker("stop", worker)
