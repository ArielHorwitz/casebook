"""CaseCoordinator: the casebook-specific brain over the generic engine.

This is the per-app coordination layer from docs/architecture.md. It maps cases
to their agents, injects the directive as system instructions when an agent is
spawned, watches case directories so user/agent edits stay visible, and brokers
the permission round-trip between an agent and the UI. The engine below it knows
nothing about cases; this layer does.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from pathlib import Path
from typing import Optional

from watchfiles import awatch

from . import cases, config, storage, templates
from .engine.events import EventBus
from .engine.session import AgentSession, SessionManager

# Event types worth replaying to a browser that connects/reloads mid-case, and
# worth persisting so a session survives a restart.
_REPLAYABLE = {"message", "tool_call", "notice", "plan"}


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


def _auto_allow_option(options: list[dict]) -> Optional[str]:
    """Pick the option to grant when a session is in always-allow mode."""
    for kind in ("allow_always", "allow_once"):
        for option in options:
            if option.get("kind") == kind:
                return option["option_id"]
    return options[0]["option_id"] if options else None


class CaseCoordinator:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.casebook_root = self.project_root.joinpath(cases.CASEBOOK_DIR)
        self.config = config.load_config(self.project_root)
        self.store = storage.SessionStore(self.project_root)
        self.bus = EventBus()
        self.sessions = SessionManager()
        self._agents: dict[str, dict] = {}
        self._transcripts: dict[str, list[dict]] = {}
        self._acp_ids: dict[str, Optional[str]] = {}
        self._created: dict[str, Optional[str]] = {}
        self._permissions: dict[str, asyncio.Future] = {}
        self._watchers: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}

    def load_persisted(self) -> None:
        """Restore every session on disk as a (non-live) stored session."""
        for stored in self.store.load_all():
            meta = stored.meta
            agent_id = meta["agent_id"]
            self._agents[agent_id] = {
                "agent_id": agent_id,
                "case_id": meta["case_id"],
                "label": meta.get("label", agent_id),
                "backend": meta.get("backend", ""),
                "always_allow": bool(meta.get("always_allow", False)),
                "state": "stored",
                "live": False,
            }
            self._acp_ids[agent_id] = meta.get("acp_session_id")
            self._created[agent_id] = meta.get("created")
            self._transcripts[agent_id] = list(stored.transcript)

    # --- single emit choke point: record, persist, then publish ----------
    def _emit(self, event: dict) -> None:
        agent_id = event.get("agent_id")
        if event.get("type") == "agent_state" and agent_id in self._agents:
            self._agents[agent_id]["state"] = event.get("state")
        if agent_id in self._agents and event.get("type") in _REPLAYABLE:
            self._transcripts.setdefault(agent_id, []).append(event)
            self.store.append_event(self._agents[agent_id]["case_id"], agent_id, event)
        self.bus.publish(event)

    def _persist_meta(self, agent_id: str) -> None:
        agent = self._agents[agent_id]
        self.store.write_meta(
            {
                "agent_id": agent_id,
                "case_id": agent["case_id"],
                "label": agent["label"],
                "backend": agent["backend"],
                "always_allow": agent.get("always_allow", False),
                "acp_session_id": self._acp_ids.get(agent_id),
                "created": self._created.get(agent_id),
                "last_active": _now_iso(),
            }
        )

    # --- cases (read-only views for the UI) ------------------------------
    def list_cases(self) -> list[dict]:
        return [self._case_summary(case) for case in cases.list_cases(self.casebook_root)]

    def case_detail(self, case_id: str) -> dict:
        case = cases.resolve_case(self.casebook_root, case_id)
        detail = self._case_summary(case)
        detail["files"] = case.files()
        detail["agents"] = [
            agent for agent in self._agents.values() if agent["case_id"] == case.case_id
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
        existing = sum(1 for a in self._agents.values() if a["case_id"] == case.case_id)
        agent_id = self.sessions.new_agent_id()
        label = label or f"Session {existing + 1}"
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
        self._created[agent_id] = _now_iso()
        self._acp_ids[agent_id] = None
        self._agents[agent_id] = {
            "agent_id": agent_id,
            "case_id": case.case_id,
            "label": label,
            "backend": backend.name,
            "always_allow": False,
            "state": "starting",
            "live": True,
        }
        self._watch_case(case)
        self._persist_meta(agent_id)
        self._emit({"type": "agent_added", **self._agents[agent_id]})
        try:
            await session.start(templates.system_instructions(case.case_id))
        except Exception as error:
            self.sessions.pop(agent_id)
            self._agents.pop(agent_id, None)
            self._acp_ids.pop(agent_id, None)
            self._created.pop(agent_id, None)
            self.store.delete(case.case_id, agent_id)
            self._emit({"type": "agent_removed", "agent_id": agent_id,
                        "case_id": case.case_id})
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": case.case_id,
                        "message": f"failed to start agent: {error}"})
            raise
        self._acp_ids[agent_id] = session.acp_session_id
        self._persist_meta(agent_id)
        return agent_id

    async def resume_agent(self, agent_id: str) -> None:
        """Bring a stored session back to life (idempotent if already live)."""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise cases.CasebookError(f"no such session: {agent_id}")
        if agent.get("live"):
            return
        case = cases.resolve_case(self.casebook_root, agent["case_id"])
        try:
            backend = self.config.select_backend(agent["backend"] or None)
        except KeyError as error:
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": f"cannot resume session: {error}"})
            raise
        session = AgentSession(
            agent_id=agent_id,
            label=agent["label"],
            case_id=agent["case_id"],
            project_root=self.project_root,
            backend=backend,
            emit=self._emit,
            request_permission=self._request_permission,
        )
        self.sessions.add(session)
        agent["state"] = "starting"
        agent["live"] = True
        self._watch_case(case)
        self._emit({"type": "agent_updated", **agent})
        try:
            await session.resume(
                templates.system_instructions(agent["case_id"]),
                self._acp_ids.get(agent_id),
            )
        except Exception as error:
            self.sessions.pop(agent_id)
            agent["state"] = "stored"
            agent["live"] = False
            self._emit({"type": "agent_updated", **agent})
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": f"failed to resume session: {error}"})
            raise
        self._acp_ids[agent_id] = session.acp_session_id
        self._persist_meta(agent_id)

    async def send(self, agent_id: str, text: str) -> None:
        session = self.sessions.get(agent_id)
        if session is None:
            raise cases.CasebookError(f"no such live session: {agent_id}")
        await session.send(text)

    async def cancel(self, agent_id: str) -> None:
        session = self.sessions.get(agent_id)
        if session is not None:
            await session.cancel()

    async def close_agent(self, agent_id: str) -> None:
        """Stop the subprocess but keep the session on disk so it can be resumed."""
        session = self.sessions.pop(agent_id)
        agent = self._agents.get(agent_id)
        if session is not None:
            await session.stop()
        if agent is not None:
            agent["state"] = "stored"
            agent["live"] = False
            self._persist_meta(agent_id)
            self._emit({"type": "agent_updated", **agent})

    async def delete_agent(self, agent_id: str) -> None:
        """Stop (if live) and erase the session and its stored history."""
        session = self.sessions.pop(agent_id)
        agent = self._agents.pop(agent_id, None)
        self._transcripts.pop(agent_id, None)
        self._acp_ids.pop(agent_id, None)
        self._created.pop(agent_id, None)
        if session is not None:
            await session.stop()
        if agent is not None:
            self.store.delete(agent["case_id"], agent_id)
            self._emit({"type": "agent_removed", "agent_id": agent_id,
                        "case_id": agent["case_id"]})

    def set_always_allow(self, agent_id: str, value: bool) -> None:
        agent = self._agents.get(agent_id)
        if agent is None:
            return
        agent["always_allow"] = bool(value)
        self._persist_meta(agent_id)
        self._emit({"type": "agent_updated", **agent})

    # --- permission round-trip (agent waits on the user) -----------------
    async def _request_permission(self, payload: dict) -> Optional[str]:
        agent_id = payload.get("agent_id")
        if agent_id and self._agents.get(agent_id, {}).get("always_allow"):
            chosen = _auto_allow_option(payload.get("options", []))
            if chosen is not None:
                tool = payload.get("tool_call", {}).get("title") or "tool call"
                self._emit({"type": "notice", "agent_id": agent_id,
                            "case_id": payload.get("case_id"),
                            "message": f"auto-allowed (always allow): {tool}"})
                return chosen
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
