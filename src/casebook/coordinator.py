"""CaseCoordinator: the casebook-specific brain over the generic engine.

This is the per-app coordination layer from docs/architecture.md. It maps cases
to their agents, injects the directive as system instructions when an agent is
spawned, watches case directories so user/agent edits stay visible, and brokers
the permission round-trip between an agent and the UI. The engine below it knows
nothing about cases; this layer does.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Optional

from watchfiles import awatch

from . import cases, config, templates
from .engine.events import EventBus
from .engine.session import AgentSession, SessionManager

# Event types worth replaying to a browser that connects/reloads mid-case.
_REPLAYABLE = {"message", "tool_call", "notice", "plan"}


class CaseCoordinator:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.casebook_root = self.project_root.joinpath(cases.CASEBOOK_DIR)
        self.config = config.load_config(self.project_root)
        self.bus = EventBus()
        self.sessions = SessionManager()
        self._agents: dict[str, dict] = {}
        self._transcripts: dict[str, list[dict]] = {}
        self._permissions: dict[str, asyncio.Future] = {}
        self._watchers: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}

    # --- single emit choke point: record, then publish -------------------
    def _emit(self, event: dict) -> None:
        agent_id = event.get("agent_id")
        if event.get("type") == "agent_state" and agent_id in self._agents:
            self._agents[agent_id]["state"] = event.get("state")
        if agent_id and event.get("type") in _REPLAYABLE:
            self._transcripts.setdefault(agent_id, []).append(event)
        self.bus.publish(event)

    # --- cases (read-only views for the UI) ------------------------------
    def list_cases(self) -> list[dict]:
        return [self._case_summary(case) for case in cases.list_cases(self.casebook_root)]

    def case_detail(self, case_id: str) -> dict:
        case = cases.resolve_case(self.casebook_root, case_id)
        detail = self._case_summary(case)
        detail["files"] = case.files()
        detail["agents"] = [
            self._agents[s.agent_id] for s in self.sessions.for_case(case.case_id)
        ]
        return detail

    def read_case_file(self, case_id: str, filename: str) -> str:
        case = cases.resolve_case(self.casebook_root, case_id)
        target = case.path.joinpath(filename).resolve()
        if target.parent != case.path.resolve():
            raise cases.CasebookError("file is not in the case directory")
        return target.read_text()

    @staticmethod
    def _case_summary(case: cases.Case) -> dict:
        return {
            "case_id": case.case_id,
            "title": case.title,
            "status": case.status,
            "keywords": case.keywords,
            "hidden": case.hidden,
        }

    # --- agents ----------------------------------------------------------
    async def add_agent(
        self,
        case_id: str,
        label: Optional[str] = None,
        backend_name: Optional[str] = None,
    ) -> str:
        case = cases.resolve_case(self.casebook_root, case_id)
        backend = self.config.select_backend(backend_name)
        existing = len(self.sessions.for_case(case.case_id))
        agent_id = self.sessions.new_agent_id()
        label = label or f"Agent {existing + 1}"
        session = AgentSession(
            agent_id=agent_id,
            label=label,
            case_id=case.case_id,
            project_root=self.project_root,
            backend=backend,
            emit=self._emit,
            request_permission=self._request_permission,
        )
        self.sessions.add(session)
        self._agents[agent_id] = {
            "agent_id": agent_id,
            "case_id": case.case_id,
            "label": label,
            "backend": backend.name,
            "state": "starting",
        }
        self._watch_case(case)
        self._emit({"type": "agent_added", **self._agents[agent_id]})
        try:
            await session.start(templates.system_instructions(case.case_id))
        except Exception as error:
            self.sessions.pop(agent_id)
            self._agents.pop(agent_id, None)
            self._emit({"type": "agent_removed", "agent_id": agent_id,
                        "case_id": case.case_id})
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": case.case_id,
                        "message": f"failed to start agent: {error}"})
            raise
        return agent_id

    async def send(self, agent_id: str, text: str) -> None:
        session = self.sessions.get(agent_id)
        if session is None:
            raise cases.CasebookError(f"no such agent: {agent_id}")
        await session.send(text)

    async def cancel(self, agent_id: str) -> None:
        session = self.sessions.get(agent_id)
        if session is not None:
            await session.cancel()

    async def remove_agent(self, agent_id: str) -> None:
        session = self.sessions.pop(agent_id)
        meta = self._agents.pop(agent_id, None)
        self._transcripts.pop(agent_id, None)
        if session is not None:
            await session.stop()
        if meta is not None:
            self._emit({"type": "agent_removed", "agent_id": agent_id,
                        "case_id": meta["case_id"]})

    # --- permission round-trip (agent waits on the user) -----------------
    async def _request_permission(self, payload: dict) -> Optional[str]:
        request_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._permissions[request_id] = future
        self._emit({"type": "permission_request", "request_id": request_id, **payload})
        try:
            return await future
        finally:
            self._permissions.pop(request_id, None)

    def resolve_permission(self, request_id: str, option_id: Optional[str]) -> None:
        future = self._permissions.get(request_id)
        if future is not None and not future.done():
            future.set_result(option_id)
        self._emit({"type": "permission_resolved", "request_id": request_id})

    # --- filesystem watching --------------------------------------------
    def _watch_case(self, case: cases.Case) -> None:
        if case.case_id in self._watchers:
            return
        stop = asyncio.Event()
        task = asyncio.create_task(self._watch_loop(case.case_id, case.path, stop))
        self._watchers[case.case_id] = (task, stop)

    async def _watch_loop(self, case_id: str, case_path: Path, stop: asyncio.Event) -> None:
        try:
            async for _changes in awatch(case_path, stop_event=stop):
                case = cases.load_case(case_path)
                self._emit({"type": "files_changed", "case_id": case_id,
                            "files": case.files()})
        except Exception as error:
            self._emit({"type": "notice", "case_id": case_id,
                        "message": f"file watcher stopped: {error}"})

    # --- lifecycle / reconnection ---------------------------------------
    def snapshot(self) -> dict:
        return {
            "type": "snapshot",
            "agents": list(self._agents.values()),
            "transcripts": self._transcripts,
        }

    async def shutdown(self) -> None:
        for _task, stop in self._watchers.values():
            stop.set()
        for session in self.sessions.all():
            await session.stop()
