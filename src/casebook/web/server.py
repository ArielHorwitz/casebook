"""Starlette app: REST for read-only case views, WebSocket for live work.

The server is project-agnostic at startup. Projects are selected through the UI;
each gets its own CaseCoordinator, lazily created and cached for the lifetime of
the process. REST endpoints under ``/api/projects/{project_id}/`` are scoped to a
single project; the project browser at ``/api/projects`` reads from the global
path cache.
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

from .. import cases, config, projects
from ..coordinator import CaseCoordinator

STATIC_DIR = Path(__file__).parent.joinpath("static")


def create_app() -> Starlette:
    coordinators: dict[str, CaseCoordinator] = {}

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        try:
            yield
        finally:
            for coordinator in coordinators.values():
                await coordinator.shutdown()

    def get_coordinator(project_id: str) -> CaseCoordinator:
        """Look up or lazily create a coordinator for the given project."""
        if project_id in coordinators:
            return coordinators[project_id]
        project_root = projects.resolve_project(project_id)
        coordinator = CaseCoordinator(project_root)
        coordinator.load_persisted()
        coordinators[project_id] = coordinator
        projects.touch_project(project_id)
        return coordinator

    # --- HTML (single document for all client-side routes) ---------------

    async def index(_request: Request) -> FileResponse:
        return FileResponse(STATIC_DIR.joinpath("index.html"))

    # --- project browser -------------------------------------------------

    async def projects_endpoint(request: Request) -> JSONResponse:
        if request.method == "POST":
            body = await request.json()
            action = body.get("action", "open")
            path = Path(body.get("path", ""))
            try:
                if action == "init":
                    entry = projects.init_project(path)
                else:
                    entry = projects.open_project(path)
                # Eagerly create the coordinator so case counts are available.
                coordinator = get_coordinator(entry["id"])
                entry["cases"] = len(coordinator.list_cases())
                return JSONResponse(entry, status_code=201)
            except cases.CasebookError as error:
                return JSONResponse({"error": str(error)}, status_code=400)
        # GET: list projects with case counts.
        entries = projects.list_projects()
        for entry in entries:
            try:
                coordinator = get_coordinator(entry["id"])
                entry["cases"] = len(coordinator.list_cases())
            except cases.CasebookError:
                entry["cases"] = 0
        return JSONResponse(entries)

    # --- project-scoped case endpoints -----------------------------------

    async def cases_endpoint(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        try:
            coordinator = get_coordinator(pid)
        except cases.CasebookError as error:
            return JSONResponse({"error": str(error)}, status_code=404)
        if request.method == "POST":
            body = await request.json()
            summary = coordinator.create_case(body.get("title", "Unnamed case"))
            return JSONResponse(summary, status_code=201)
        return JSONResponse(coordinator.list_cases())

    async def promote(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        try:
            coordinator = get_coordinator(pid)
        except cases.CasebookError as error:
            return JSONResponse({"error": str(error)}, status_code=404)
        body = await request.json()
        new_case_id = await coordinator.promote_agent(
            body["agent_id"], body.get("title", "Unnamed case")
        )
        if new_case_id is None:
            return JSONResponse({"error": "not a scratch session"}, status_code=400)
        return JSONResponse({"case_id": new_case_id}, status_code=201)

    async def list_backends(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        try:
            coordinator = get_coordinator(pid)
        except cases.CasebookError as error:
            return JSONResponse({"error": str(error)}, status_code=404)
        return JSONResponse(coordinator.list_backends())

    async def global_hotkeys(_request: Request) -> JSONResponse:
        return JSONResponse(config.global_hotkeys())

    async def hotkeys(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        try:
            coordinator = get_coordinator(pid)
        except cases.CasebookError as error:
            return JSONResponse({"error": str(error)}, status_code=404)
        return JSONResponse(coordinator.hotkeys())

    async def ui_config(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        try:
            coordinator = get_coordinator(pid)
        except cases.CasebookError as error:
            return JSONResponse({"error": str(error)}, status_code=404)
        return JSONResponse(coordinator.ui_config())

    async def case_detail(request: Request) -> JSONResponse:
        pid = request.path_params["project_id"]
        case_id = request.path_params["case_id"]
        try:
            coordinator = get_coordinator(pid)
            if request.method == "DELETE":
                await coordinator.delete_case(case_id)
                return JSONResponse({"deleted": case_id})
            return JSONResponse(coordinator.case_detail(case_id))
        except cases.CasebookError as error:
            return JSONResponse({"error": str(error)}, status_code=404)

    async def case_file(request: Request):
        pid = request.path_params["project_id"]
        try:
            coordinator = get_coordinator(pid)
            content = coordinator.read_case_file(
                request.path_params["case_id"], request.path_params["filename"]
            )
            return PlainTextResponse(content)
        except (cases.CasebookError, OSError) as error:
            return PlainTextResponse(str(error), status_code=404)

    # --- WebSocket (project-scoped) --------------------------------------

    async def websocket_endpoint(websocket: WebSocket) -> None:
        pid = websocket.path_params["project_id"]
        try:
            coordinator = get_coordinator(pid)
        except cases.CasebookError:
            await websocket.close(code=4000, reason="unknown project")
            return
        await websocket.accept()
        await _run_socket(websocket, coordinator)

    return Starlette(
        lifespan=lifespan,
        routes=[
            # Project browser
            Route("/api/projects", projects_endpoint, methods=["GET", "POST"]),
            Route("/api/hotkeys", global_hotkeys),
            # Project-scoped API
            Route("/api/projects/{project_id}/cases", cases_endpoint,
                  methods=["GET", "POST"]),
            Route("/api/projects/{project_id}/cases/{case_id}", case_detail,
                  methods=["GET", "DELETE"]),
            Route("/api/projects/{project_id}/cases/{case_id}/files/{filename}",
                  case_file),
            Route("/api/projects/{project_id}/promote", promote, methods=["POST"]),
            Route("/api/projects/{project_id}/backends", list_backends),
            Route("/api/projects/{project_id}/hotkeys", hotkeys),
            Route("/api/projects/{project_id}/ui", ui_config),
            # Project-scoped WebSocket
            WebSocketRoute("/ws/{project_id}", websocket_endpoint),
            # Static assets
            Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
            # Catch-all: serve index.html for all client-side routes.
            Route("/", index),
            Route("/project/{project_id:path}", index),
        ],
    )


async def _run_socket(websocket: WebSocket, coordinator: CaseCoordinator) -> None:
    """Pump coordinator events out and user actions in until the socket closes."""
    with coordinator.bus.subscribe() as queue:
        await websocket.send_json(coordinator.snapshot())
        sender = asyncio.create_task(_send_events(websocket, queue))
        try:
            while True:
                action = await websocket.receive_json()
                _dispatch(coordinator, action)
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()


async def _send_events(websocket: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        event = await queue.get()
        await websocket.send_json(event)


def _dispatch(coordinator: CaseCoordinator, action: dict) -> None:
    name = action.get("action")
    if name == "add_agent":
        _spawn(coordinator.add_agent(action["case_id"], action.get("label"),
                                     action.get("backend")))
    elif name == "resume_agent":
        _spawn(coordinator.resume_agent(action["agent_id"]))
    elif name == "rename_agent":
        coordinator.rename_agent(action["agent_id"], action.get("label", ""))
    elif name == "name_agent":
        _spawn(coordinator.name_agent(action["agent_id"]))
    elif name == "set_model":
        _spawn(coordinator.set_model(action["agent_id"], action["model_id"]))
    elif name == "send":
        _spawn(coordinator.send(action["agent_id"], action["text"]))
    elif name == "cancel":
        _spawn(coordinator.cancel(action["agent_id"]))
    elif name == "close_agent":
        _spawn(coordinator.close_agent(action["agent_id"]))
    elif name == "delete_agent":
        _spawn(coordinator.delete_agent(action["agent_id"]))
    elif name == "permission":
        coordinator.resolve_permission(action["request_id"], action.get("option_id"))
    elif name == "set_always_allow":
        coordinator.set_always_allow(action["agent_id"], action.get("value", False))
    elif name == "revert_agent":
        _spawn(coordinator.revert_agent(action["agent_id"], action["event_index"]))
    elif name == "fork_agent":
        _spawn(coordinator.fork_agent(action["agent_id"], action.get("event_index")))


def _spawn(coro) -> None:
    """Run a coordinator coroutine in the background; errors become notices."""
    asyncio.create_task(_guard(coro))


async def _guard(coro) -> None:
    try:
        await coro
    except Exception:  # already surfaced as notices where it matters
        pass


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    print(f"casebook serving on http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
