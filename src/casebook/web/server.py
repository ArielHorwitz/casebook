"""Starlette app: REST for read-only case views, WebSocket for live work.

The WebSocket is the live spine — it carries every engine event out to the
browser and every user action back in. REST is only for the cheap read-only
snapshots (case list, case detail, file contents) the browser fetches on
navigation. Slow actions (spawning an agent, a prompt turn) are dispatched as
background tasks so the socket stays responsive; their progress comes back as
events like any other.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from .. import cases
from ..coordinator import CaseCoordinator

STATIC_DIR = Path(__file__).parent.joinpath("static")


def create_app(project_root: Path) -> Starlette:
    coordinator: dict = {}  # filled on startup so it lives on the running loop

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        instance = CaseCoordinator(project_root)
        instance.load_persisted()
        coordinator["instance"] = instance
        try:
            yield
        finally:
            await instance.shutdown()

    def engine() -> CaseCoordinator:
        return coordinator["instance"]

    async def index(_request: Request) -> FileResponse:
        return FileResponse(STATIC_DIR.joinpath("index.html"))

    async def list_cases(_request: Request) -> JSONResponse:
        return JSONResponse(engine().list_cases())

    async def case_detail(request: Request) -> JSONResponse:
        try:
            return JSONResponse(engine().case_detail(request.path_params["case_id"]))
        except cases.CasebookError as error:
            return JSONResponse({"error": str(error)}, status_code=404)

    async def case_file(request: Request):
        try:
            content = engine().read_case_file(
                request.path_params["case_id"], request.path_params["filename"]
            )
            return PlainTextResponse(content)
        except (cases.CasebookError, OSError) as error:
            return PlainTextResponse(str(error), status_code=404)

    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await _run_socket(websocket, engine())

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/", index),
            Route("/api/cases", list_cases),
            Route("/api/cases/{case_id}", case_detail),
            Route("/api/cases/{case_id}/files/{filename}", case_file),
            WebSocketRoute("/ws", websocket_endpoint),
            Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
        ],
    )


async def _run_socket(websocket: WebSocket, engine: CaseCoordinator) -> None:
    """Pump engine events out and user actions in until the socket closes."""
    with engine.bus.subscribe() as queue:
        await websocket.send_json(engine.snapshot())
        sender = asyncio.create_task(_send_events(websocket, queue))
        try:
            while True:
                action = await websocket.receive_json()
                _dispatch(engine, action)
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()


async def _send_events(websocket: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        event = await queue.get()
        await websocket.send_json(event)


def _dispatch(engine: CaseCoordinator, action: dict) -> None:
    name = action.get("action")
    if name == "add_agent":
        _spawn(engine.add_agent(action["case_id"], action.get("label"),
                                action.get("backend")))
    elif name == "resume_agent":
        _spawn(engine.resume_agent(action["agent_id"]))
    elif name == "rename_agent":
        engine.rename_agent(action["agent_id"], action.get("label", ""))
    elif name == "name_agent":
        _spawn(engine.name_agent(action["agent_id"]))
    elif name == "send":
        _spawn(engine.send(action["agent_id"], action["text"]))
    elif name == "cancel":
        _spawn(engine.cancel(action["agent_id"]))
    elif name == "close_agent":
        _spawn(engine.close_agent(action["agent_id"]))
    elif name == "delete_agent":
        _spawn(engine.delete_agent(action["agent_id"]))
    elif name == "permission":
        engine.resolve_permission(action["request_id"], action.get("option_id"))
    elif name == "set_always_allow":
        engine.set_always_allow(action["agent_id"], action.get("value", False))


def _spawn(coro) -> None:
    """Run a coordinator coroutine in the background; errors become notices."""
    asyncio.create_task(_guard(coro))


async def _guard(coro) -> None:
    try:
        await coro
    except Exception:  # already surfaced as notices where it matters
        pass


def serve(project_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(create_app(project_root), host=host, port=port, log_level="warning")
