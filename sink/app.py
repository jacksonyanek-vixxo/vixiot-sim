"""FastAPI dashboard server backed by the shared MQTT sink hub."""

import argparse
import asyncio
import importlib.util
import os
import sys
import sysconfig
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_stdlib_secrets():
    """Prevent the project's device secrets.py from shadowing the stdlib module."""
    loaded = sys.modules.get("secrets")
    stdlib = Path(sysconfig.get_path("stdlib"))
    if loaded and Path(getattr(loaded, "__file__", "")).parent == stdlib:
        return
    spec = importlib.util.spec_from_file_location("secrets", stdlib / "secrets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["secrets"] = module
    spec.loader.exec_module(module)


_load_stdlib_secrets()

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sink.hub import SinkHub

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def hub_from_env():
    port = int(os.getenv("VIXIOT_MQTT_PORT", "1883"))
    return SinkHub(
        broker=os.getenv("VIXIOT_BROKER", "localhost"),
        port=port,
        username=os.getenv("VIXIOT_MQTT_USER"),
        password=os.getenv("VIXIOT_MQTT_PASSWORD"),
        tls=_env_bool("VIXIOT_MQTT_TLS", port == 8883),
    )


class WebSocketBroadcaster:
    def __init__(self):
        self.clients = set()
        self.queue = None
        self.loop = None
        self.task = None

    def start(self):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.task = asyncio.create_task(self._drain())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None

    def enqueue(self, event):
        if self.loop and self.queue:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    async def _drain(self):
        while True:
            event = await self.queue.get()
            stale = []
            for socket in tuple(self.clients):
                try:
                    await socket.send_json(event)
                except Exception:
                    stale.append(socket)
            for socket in stale:
                self.clients.discard(socket)


def create_app(hub=None, manage_hub=True):
    sink_hub = hub or hub_from_env()
    broadcaster = WebSocketBroadcaster()

    @asynccontextmanager
    async def lifespan(application):
        broadcaster.start()
        sink_hub.set_broadcast(broadcaster.enqueue)
        if manage_hub:
            sink_hub.start()
        try:
            yield
        finally:
            if manage_hub:
                sink_hub.stop()
            await broadcaster.stop()

    application = FastAPI(
        title="VixIoT Dashboard",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.hub = sink_hub
    application.state.broadcaster = broadcaster

    @application.get("/api/devices")
    def devices():
        return sink_hub.devices()

    @application.get("/api/snapshot/{device_id}")
    def snapshot(device_id):
        result = sink_hub.snapshot(device_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return result

    @application.get("/api/telemetry/{device_id}")
    def telemetry(device_id):
        return sink_hub.telemetry(device_id)

    @application.get("/api/workorders/{device_id}")
    def workorders(device_id):
        return sink_hub.workorders(device_id)

    @application.post("/api/config/{device_id}")
    def set_config(device_id, config: dict):
        try:
            command = sink_hub.set_config(device_id, config)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"accepted": True, "command": command}

    @application.websocket("/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        broadcaster.clients.add(socket)
        await socket.send_json({"type": "backfill", "devices": sink_hub.backfill()})
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            broadcaster.clients.discard(socket)

    @application.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    application.mount(
        "/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static"
    )
    return application


app = create_app()


def main():
    parser = argparse.ArgumentParser(description="VixIoT web dashboard")
    parser.add_argument("--broker", default=os.getenv("VIXIOT_BROKER", "localhost"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("VIXIOT_MQTT_PORT", "1883"))
    )
    parser.add_argument("--tls", action="store_true", default=_env_bool("VIXIOT_MQTT_TLS"))
    parser.add_argument("--user", default=os.getenv("VIXIOT_MQTT_USER"))
    parser.add_argument("--password", default=os.getenv("VIXIOT_MQTT_PASSWORD"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=8000)
    args = parser.parse_args()

    dashboard_hub = SinkHub(
        args.broker,
        args.port,
        username=args.user,
        password=args.password,
        tls=args.tls or args.port == 8883,
    )
    uvicorn.run(
        create_app(dashboard_hub),
        host=args.host,
        port=args.web_port,
    )


if __name__ == "__main__":
    main()
