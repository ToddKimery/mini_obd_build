"""
Mini OBD FastAPI backend.
Serves the WebSocket stream, REST API, and Next.js static export.
"""
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles

from obd_manager import OBDManager

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
