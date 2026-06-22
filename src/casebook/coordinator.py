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
from .engine import oneshot
from .engine.events import EventBus
from .engine.session import AgentSession, SessionManager

# Event types worth replaying to a browser that connects/reloads mid-case, and
# worth persisting so a session survives a restart.
_REPLAYABLE = {"message", "tool_call", "notice", "plan"}


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


def _match_model(preference: Optional[str], available: list[dict]) -> Optional[str]:
    """Resolve a loose model preference (id or name substring) to an available id."""
    if not preference or not available:
        return None
    ids = [model["model_id"] for model in available]
    if preference in ids:
        return preference
    lowered = preference.lower()
    for model in available:
        if lowered in model["model_id"].lower() or lowered in (model.get("name") or "").lower():
            return model["model_id"]
    return None


def _clean_name(reply: str) -> str:
    """Reduce a model reply to a single short label."""
    first_line = reply.strip().splitlines()[0] if reply.strip() else ""
    return first_line.strip().strip("\"'").strip()[:80]


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
        self._models: dict[str, list[dict]] = {}
        # Transcript to prepend to a resumed session's next message, for backends
        # that lack native session/load. Keyed by agent_id, consumed once.
        self._pending_context: dict[str, str] = {}
        # Whether a session still has its auto-assigned name, and which sessions
        # have been written to disk. A session with no messages and an auto name is
        # "trivial" — identical to a brand-new one — and is never persisted.
        self._auto_named: dict[str, bool] = {}
        self._persisted: set[str] = set()
        # Latest usage (context size/used, token totals, cost) per session, merged
        # from ACP usage updates and prompt responses.
        self._usage: dict[str, dict] = {}
        # Which sessions are currently busy, for console activity reporting.
        self._busy_ids: set[str] = set()
        self._permissions: dict[str, asyncio.Future] = {}
        self._watchers: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}

    def load_persisted(self) -> None:
        """Restore every session on disk as a (non-live) stored session.

        Everything on disk is loaded as-is — startup never deletes sessions. (New
        trivial sessions simply aren't written in the first place; see _emit.)
        """
        for stored in self.store.load_all():
            meta = stored.meta
            agent_id = meta["agent_id"]
            named = bool(meta.get("named", False))
            self._agents[agent_id] = {
                "agent_id": agent_id,
                "case_id": meta["case_id"],
                "label": meta.get("label", agent_id),
                "backend": meta.get("backend", ""),
                "model": meta.get("model"),
                "always_allow": bool(meta.get("always_allow", False)),
                "state": "stored",
                "live": False,
            }
            self._acp_ids[agent_id] = meta.get("acp_session_id")
            self._created[agent_id] = meta.get("created")
            self._auto_named[agent_id] = not named
            self._persisted.add(agent_id)
            self._transcripts[agent_id] = list(stored.transcript)

    def _should_persist(self, agent_id: str) -> bool:
        """A session is worth saving once it has a message or a custom name."""
        if not self._auto_named.get(agent_id, True):
            return True
        return any(
            event.get("type") == "message"
            for event in self._transcripts.get(agent_id, [])
        )

    # --- single emit choke point: record, persist, then publish ----------
    def _emit(self, event: dict) -> None:
        agent_id = event.get("agent_id")
        event_type = event.get("type")
        if event_type == "agent_state" and agent_id in self._agents:
            self._agents[agent_id]["state"] = event.get("state")
        if event_type == "usage" and agent_id in self._agents:
            merged = self._usage.setdefault(agent_id, {})
            for key, value in event.items():
                if key not in ("type", "agent_id", "case_id") and value is not None:
                    merged[key] = value
        if agent_id in self._agents and event_type in _REPLAYABLE:
            self._transcripts.setdefault(agent_id, []).append(event)
            # Only commit to disk once the session is non-trivial; the first real
            # content writes the metadata so meta.toml and the transcript stay paired.
            if agent_id in self._persisted or self._should_persist(agent_id):
                self._persist_meta(agent_id)
                self.store.append_event(self._agents[agent_id]["case_id"], agent_id, event)
        self.bus.publish(event)
        if event_type in ("agent_state", "agent_added", "agent_updated", "agent_removed"):
            self._report_activity()

    def _report_activity(self) -> None:
        """Print a console line when the set of busy sessions changes.

        Lets you glance at the terminal running `casebook serve` before Ctrl+C to
        see whether any session is still working.
        """
        busy = {
            agent_id
            for agent_id, agent in self._agents.items()
            if agent.get("live") and agent.get("state") in ("starting", "working")
        }
        if busy == self._busy_ids:
            return
        self._busy_ids = busy
        if not busy:
            print("[casebook] all sessions idle", flush=True)
        else:
            running = ", ".join(
                f"{self._agents[a]['label']} ({self._agents[a]['state']})" for a in busy
            )
            print(f"[casebook] {len(busy)} session(s) running: {running}", flush=True)

    def _persist_meta(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            return
        if agent_id not in self._persisted and not self._should_persist(agent_id):
            return  # trivial session: keep it off disk entirely
        self._persisted.add(agent_id)
        agent = self._agents[agent_id]
        self.store.write_meta(
            {
                "agent_id": agent_id,
                "case_id": agent["case_id"],
                "label": agent["label"],
                "backend": agent["backend"],
                "model": agent.get("model"),
                "always_allow": agent.get("always_allow", False),
                "named": not self._auto_named.get(agent_id, True),
                "acp_session_id": self._acp_ids.get(agent_id),
                "created": self._created.get(agent_id),
                "last_active": _now_iso(),
            }
        )

    # --- cases (read-only views for the UI) ------------------------------
    def list_cases(self) -> list[dict]:
        return [self._case_summary(case) for case in cases.list_cases(self.casebook_root)]

    def list_backends(self) -> dict:
        return {
            "backends": sorted(self.config.backends),
            "default": self.config.default_backend,
        }

    def hotkeys(self) -> dict:
        return dict(self.config.hotkeys)

    def ui_config(self) -> dict:
        return dict(self.config.ui)

    def create_case(self, title: str) -> dict:
        """Create a case on disk and announce it so open browsers refresh."""
        case = cases.create_case(self.casebook_root, title or "Unnamed case")
        summary = self._case_summary(case)
        self._emit({"type": "case_created", **summary})
        return summary

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
        self._auto_named[agent_id] = True
        self._agents[agent_id] = {
            "agent_id": agent_id,
            "case_id": case.case_id,
            "label": label,
            "backend": backend.name,
            "model": None,
            "always_allow": False,
            "state": "starting",
            "live": True,
        }
        self._watch_case(case)
        self._persist_meta(agent_id)
        self._emit({"type": "agent_added", **self._agents[agent_id]})
        try:
            await session.start()
        except Exception as error:
            self.sessions.pop(agent_id)
            self._agents.pop(agent_id, None)
            self._acp_ids.pop(agent_id, None)
            self._created.pop(agent_id, None)
            self._auto_named.pop(agent_id, None)
            self._persisted.discard(agent_id)
            self.store.delete(case.case_id, agent_id)
            self._emit({"type": "agent_removed", "agent_id": agent_id,
                        "case_id": case.case_id})
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": case.case_id,
                        "message": f"failed to start agent: {error}"})
            raise
        self._acp_ids[agent_id] = session.acp_session_id
        await self._apply_models(agent_id, session)
        # The directive is prepended to the first user message rather than sent as
        # its own turn, so a new session doesn't query the agent until the user does.
        self._pending_context[agent_id] = templates.system_instructions(case.case_id)
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
            loaded = await session.resume(self._acp_ids.get(agent_id))
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
        await self._apply_models(agent_id, session)
        self._persist_meta(agent_id)
        if not loaded:
            # No native session/load: re-send the directive + saved transcript as
            # context on the next message, and say the continuity is imperfect.
            self._pending_context[agent_id] = (
                f"{templates.system_instructions(agent['case_id'])}\n\n"
                f"{self._context_prompt(agent_id)}"
            )
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": "Context re-sent from saved transcript "
                                   "imperfectly — this backend has no native "
                                   "session loading."})

    def _context_prompt(self, agent_id: str) -> str:
        """Frame the saved transcript as context for a non-natively-resumed session."""
        body = self._transcript_text(agent_id, limit=24000)
        return (
            "You are resuming a previous session that was interrupted. This backend "
            "cannot restore it natively, so below is a transcript of the prior "
            "conversation, for context. Tool calls and file edits from before are "
            "not included — re-read files as needed. Continue from where this left "
            "off.\n\n=== prior conversation ===\n"
            f"{body}\n=== end of prior conversation ==="
        )

    async def _apply_models(self, agent_id: str, session: AgentSession) -> None:
        """Apply the configured default-model preference and publish the model list."""
        desired = _match_model(self.config.default_model, session.available_models)
        if desired and desired != session.current_model:
            try:
                await session.set_model(desired)
            except Exception as error:
                self._emit({"type": "notice", "agent_id": agent_id,
                            "case_id": self._agents[agent_id]["case_id"],
                            "message": f"could not select default model: {error}"})
        self._models[agent_id] = session.available_models
        self._agents[agent_id]["model"] = session.current_model
        self._emit({"type": "models", "agent_id": agent_id,
                    "case_id": self._agents[agent_id]["case_id"],
                    "available": session.available_models,
                    "current": session.current_model})

    async def set_model(self, agent_id: str, model_id: str) -> None:
        session = self.sessions.get(agent_id)
        agent = self._agents.get(agent_id)
        if session is None or agent is None:
            return
        try:
            await session.set_model(model_id)
        except Exception as error:
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": f"could not set model: {error}"})
            return
        agent["model"] = model_id
        self._persist_meta(agent_id)
        self._emit({"type": "models", "agent_id": agent_id, "case_id": agent["case_id"],
                    "available": self._models.get(agent_id, []), "current": model_id})

    def rename_agent(self, agent_id: str, label: str) -> None:
        agent = self._agents.get(agent_id)
        label = (label or "").strip()
        if agent is None or not label:
            return
        agent["label"] = label
        self._auto_named[agent_id] = False  # a custom name makes it worth keeping
        self._persist_meta(agent_id)
        self._emit({"type": "agent_updated", **agent})

    async def name_agent(self, agent_id: str) -> None:
        """Ask the model to name a session from its transcript (configurable prompt)."""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise cases.CasebookError(f"no such session: {agent_id}")
        transcript_text = self._transcript_text(agent_id)
        if not transcript_text.strip():
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": "nothing to name yet — the session has no messages"})
            return
        # Echo has no language model, so it is never used to name a session. The
        # naming backend defaults to the session's own backend when that isn't echo.
        naming_backend = self.config.naming_backend or agent["backend"]
        if not naming_backend or naming_backend == config.ECHO_BACKEND_NAME:
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": "session naming needs a non-echo backend — set "
                                   "naming_backend in config.toml"})
            return
        try:
            backend = self.config.select_backend(naming_backend)
        except KeyError as error:
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": f"cannot name session: {error}"})
            return
        prompt = f"{self.config.naming_prompt}\n\n--- transcript ---\n{transcript_text}"
        self._emit({"type": "notice", "agent_id": agent_id,
                    "case_id": agent["case_id"], "message": "naming session…"})
        try:
            reply = await oneshot.one_shot(
                backend, self.project_root, prompt, model=self.config.naming_model
            )
        except Exception as error:
            self._emit({"type": "notice", "agent_id": agent_id,
                        "case_id": agent["case_id"],
                        "message": f"naming failed: {error}"})
            return
        name = _clean_name(reply)
        if name:
            self.rename_agent(agent_id, name)

    def _transcript_text(self, agent_id: str, limit: int = 6000) -> str:
        """Plain user/agent text of a session, most recent `limit` characters."""
        lines = []
        for event in self._transcripts.get(agent_id, []):
            if event.get("type") != "message" or event.get("system"):
                continue
            role = event.get("role")
            if role in ("user", "agent"):
                lines.append(f"{role}: {event.get('text', '')}")
        return "\n".join(lines)[-limit:]

    async def send(self, agent_id: str, text: str) -> None:
        session = self.sessions.get(agent_id)
        if session is None:
            raise cases.CasebookError(f"no such live session: {agent_id}")
        pending = self._pending_context.pop(agent_id, None)
        if pending:
            # Attach the re-sent transcript to the agent's turn, but show only the
            # user's own message in the transcript (the history is already visible).
            await session.send(
                f"{pending}\n\n=== the user's message follows ===\n{text}",
                display_text=text,
            )
        else:
            await session.send(text)

    async def cancel(self, agent_id: str) -> None:
        session = self.sessions.get(agent_id)
        if session is not None:
            await session.cancel()

    async def close_agent(self, agent_id: str) -> None:
        """Collapse a session to stored, or discard it if it's trivial.

        A session with no messages and an auto name is identical to a brand-new
        one, so closing it deletes it rather than leaving a pointless resumable.
        """
        if agent_id in self._agents and not self._should_persist(agent_id):
            await self.delete_agent(agent_id)
            return
        session = self.sessions.pop(agent_id)
        agent = self._agents.get(agent_id)
        if session is not None:
            await session.stop()
        if agent is not None:
            agent["state"] = "stored"
            agent["live"] = False
            self._models.pop(agent_id, None)
            self._pending_context.pop(agent_id, None)
            self._persist_meta(agent_id)
            self._emit({"type": "agent_updated", **agent})

    async def delete_agent(self, agent_id: str) -> None:
        """Stop (if live) and erase the session and its stored history."""
        session = self.sessions.pop(agent_id)
        agent = self._agents.pop(agent_id, None)
        self._transcripts.pop(agent_id, None)
        self._acp_ids.pop(agent_id, None)
        self._created.pop(agent_id, None)
        self._models.pop(agent_id, None)
        self._pending_context.pop(agent_id, None)
        self._auto_named.pop(agent_id, None)
        self._persisted.discard(agent_id)
        self._usage.pop(agent_id, None)
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
            "models": self._models,
            "usage": self._usage,
        }

    async def shutdown(self) -> None:
        for _task, stop in self._watchers.values():
            stop.set()
        for session in self.sessions.all():
            await session.stop()
