"""
Mini OBD FastAPI backend.
Serves the WebSocket stream, REST API, and Next.js static export.
"""
import asyncio
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles

from obd_manager import OBDManager
from report import generate as generate_report
import ai_report as ai_report_module

app = FastAPI(title="Mini OBD API", docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

obd_mgr = OBDManager()


# ── WebSocket broadcast manager ───────────────────────────────────────────────

class WSManager:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws) if hasattr(self._clients, "discard") else None
        if ws in self._clients:
            self._clients.remove(ws)

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

ws_mgr = WSManager()


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    obd_mgr.set_loop(asyncio.get_running_loop())
    asyncio.create_task(_broadcast_loop())


async def _broadcast_loop() -> None:
    while True:
        try:
            data = await asyncio.wait_for(obd_mgr.data_queue.get(), timeout=2.0)
            await ws_mgr.broadcast(data)
        except asyncio.TimeoutError:
            if ws_mgr._clients:
                await ws_mgr.broadcast({"type": "heartbeat", **obd_mgr.status()})
        except Exception:
            pass


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_mgr.connect(ws)
    await ws.send_json({"type": "status", **obd_mgr.status()})
    try:
        while True:
            await ws.receive_text()  # keep-alive ping from client
    except WebSocketDisconnect:
        ws_mgr.disconnect(ws)


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status() -> dict:
    return obd_mgr.status()


@app.post("/api/logger/start")
async def start_logger(port: Optional[str] = None) -> dict:
    result = await obd_mgr.start(port=port)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/api/logger/mock")
async def start_mock() -> dict:
    result = await obd_mgr.start(mock=True)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/api/logger/stop")
async def stop_logger() -> dict:
    return await obd_mgr.stop()


@app.get("/api/sessions")
async def list_sessions() -> list:
    return obd_mgr.get_sessions()


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: int) -> dict:
    data = obd_mgr.get_session_data(session_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


@app.patch("/api/sessions/{session_id}/lock")
async def set_session_lock(session_id: int, body: dict) -> dict:
    locked = bool(body.get("locked", False))
    result = obd_mgr.lock_session(session_id, locked)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: int) -> dict:
    result = obd_mgr.delete_session(session_id)
    if "error" in result:
        code = 403 if "locked" in result["error"] else 404
        raise HTTPException(status_code=code, detail=result["error"])
    return result


@app.get("/api/sessions/{session_id}/report")
async def get_report(session_id: int) -> dict:
    data = obd_mgr.get_session_data(session_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return generate_report(data["session"], data["readings"])


@app.post("/api/sync-time")
async def sync_time(body: dict) -> dict:
    """Set Pi system clock from phone time. Tries without/with sudo for Docker vs Pi."""
    iso = body.get("iso", "").strip()
    if not iso:
        return {"ok": False, "error": "missing iso"}
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        utc_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        # Try in order: root (Docker), sudoed lola (Pi service)
        for cmd in (
            ["timedatectl", "set-time", utc_str],
            ["sudo", "timedatectl", "set-time", utc_str],
            ["date", "-s", utc_str],
            ["sudo", "date", "-s", utc_str],
        ):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    return {"ok": True, "set_to": utc_str}
            except (FileNotFoundError, PermissionError):
                continue
        return {"ok": False, "error": "all time-set methods failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/config/api-key/status")
async def api_key_status() -> dict:
    key_file = Path.home() / "mini_obd" / "config" / "anthropic_key.txt"
    env_set = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    file_set = key_file.exists() and bool(key_file.read_text().strip())
    return {"configured": env_set or file_set, "source": "env" if env_set else ("file" if file_set else None)}


@app.post("/api/config/api-key")
async def set_api_key(body: dict) -> dict:
    key = body.get("key", "").strip()
    key_file = Path.home() / "mini_obd" / "config" / "anthropic_key.txt"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key:
        key_file.write_text(key)
    else:
        key_file.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/ai-report")
async def get_cached_ai_report(session_id: int) -> dict:
    cached = obd_mgr.get_cached_ai_report(session_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No AI report saved for this session")
    return {
        "text":          cached["text"],
        "model":         cached["model"],
        "input_tokens":  cached["input_tokens"],
        "output_tokens": cached["output_tokens"],
        "cached":        True,
        "created_at":    cached["created_at"],
    }


@app.post("/api/sessions/{session_id}/ai-report")
async def generate_ai_report(session_id: int, force: bool = False) -> dict:
    data = obd_mgr.get_session_data(session_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])

    # Return cached version unless caller explicitly requests regeneration
    if not force:
        cached = obd_mgr.get_cached_ai_report(session_id)
        if cached:
            return {
                "text":          cached["text"],
                "model":         cached["model"],
                "input_tokens":  cached["input_tokens"],
                "output_tokens": cached["output_tokens"],
                "cached":        True,
                "created_at":    cached["created_at"],
            }

    rule = generate_report(data["session"], data["readings"])
    result = await asyncio.get_running_loop().run_in_executor(
        None, lambda: ai_report_module.generate(rule)
    )

    if "error" not in result:
        created_at = obd_mgr.save_ai_report(session_id, result)
        result["cached"] = False
        result["created_at"] = created_at

    return result


@app.get("/api/version")
async def get_version() -> dict:
    repo = Path(__file__).parent.parent.parent  # mini_obd_build root or /root/mini_obd
    # Try live git first (Pi deployment)
    try:
        version = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, cwd=repo, timeout=3,
        ).stdout.strip()
        date = subprocess.run(
            ["git", "log", "-1", "--format=%cd", "--date=short"],
            capture_output=True, text=True, cwd=repo, timeout=3,
        ).stdout.strip()
        if version:
            return {"version": version, "date": date}
    except Exception:
        pass
    # Fall back to baked-in VERSION file (Docker image)
    version_file = Path.home() / "mini_obd" / "VERSION"
    if version_file.exists():
        lines = version_file.read_text().splitlines()
        return {"version": lines[0] if lines else "dev", "date": lines[1] if len(lines) > 1 else ""}
    return {"version": "dev", "date": ""}


@app.post("/api/update")
async def trigger_update(force: bool = True) -> dict:
    """Start update.sh in the background. The script survives service restart."""
    script = Path(__file__).parent.parent.parent / "scripts" / "update.sh"
    if not script.exists():
        return {"ok": False, "error": "update.sh not found"}
    log_path = Path.home() / "mini_obd" / "logs" / "update.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["bash", str(script)]
    if force:
        cmd.append("--force")
    subprocess.Popen(
        cmd,
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,  # detach so it survives uvicorn restart
    )
    return {"ok": True}


@app.get("/api/update/log")
async def get_update_log(lines: int = 60) -> dict:
    log_path = Path.home() / "mini_obd" / "logs" / "update.log"
    if not log_path.exists():
        return {"lines": []}
    with open(log_path) as f:
        all_lines = f.readlines()
    return {"lines": [l.rstrip() for l in all_lines[-lines:]]}


@app.get("/api/sessions/{session_id}/plot")
async def get_plot(session_id: int) -> Response:
    png = obd_mgr.get_or_generate_plot(session_id)
    if png is None:
        raise HTTPException(status_code=404, detail="No data or matplotlib unavailable")
    return Response(content=png, media_type="image/png")


# ── Static Next.js export (must be last — catches all unmatched routes) ───────

_WEB_OUT = Path(__file__).parent.parent / "web" / "out"
if _WEB_OUT.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_OUT), html=True), name="static")
