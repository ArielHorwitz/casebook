"""Agent sessions: one ACP subprocess per agent, and a manager over the set.

Design choice (see decisions doc): each agent is its *own* subprocess with its
own ACP connection and single session. This gives true concurrency and
independent lifecycles for the multiple agents that may work one case at once.
They are deliberately uncoordinated with each other — they sync through the
filesystem, never through a shared connection. The cost is one node process per
agent; acceptable, and swappable later for shared-connection multiplexing.
"""

from __future__ import annotations

import os
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.interfaces import ClientCapabilities, Implementation
from acp.schema import FileSystemCapabilities

from ..config import Backend
from .client import AgentClient, Emit, PermissionRequester

CLIENT_CAPABILITIES = ClientCapabilities(
    fs=FileSystemCapabilities(read_text_file=True, write_text_file=True),
    terminal=False,
)


@dataclass
class AgentSession:
    agent_id: str
    label: str
    case_id: str
    project_root: Path
    backend: Backend
    emit: Emit
    request_permission: PermissionRequester

    _stack: AsyncExitStack = field(default_factory=AsyncExitStack, init=False)
    _conn: Any = field(default=None, init=False)
    _acp_session_id: Optional[str] = field(default=None, init=False)
    _busy: bool = field(default=False, init=False)
    _supports_load: bool = field(default=False, init=False)
    _suppress_emit: bool = field(default=False, init=False)

    @property
    def acp_session_id(self) -> Optional[str]:
        return self._acp_session_id

    def _guarded_emit(self, event: dict) -> None:
        # Dropped while replaying a loaded session — that history is already on
        # disk, so re-emitting it would duplicate the transcript.
        if not self._suppress_emit:
            self.emit(event)

    async def _spawn(self) -> None:
        """Spawn the subprocess, initialize the connection, note its capabilities."""
        client = AgentClient(
            self.agent_id,
            self.case_id,
            self.project_root,
            self._guarded_emit,
            self.request_permission,
        )
        # The backend is the user's own trusted agent; pass the full environment
        # (not the trimmed MCP default) so it keeps PATH and ambient auth.
        environment = {**os.environ, **self.backend.env}
        command, *args = self.backend.command
        conn, _process = await self._stack.enter_async_context(
            spawn_agent_process(
                client,
                command,
                *args,
                cwd=str(self.project_root),
                env=environment,
            )
        )
        self._conn = conn
        initialized = await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=CLIENT_CAPABILITIES,
            client_info=Implementation(name="casebook", version="0.1.0"),
        )
        capabilities = getattr(initialized, "agent_capabilities", None)
        self._supports_load = bool(getattr(capabilities, "load_session", False))

    async def start(self, system_instructions: str) -> None:
        """Spawn the agent, open a fresh session, and inject system instructions."""
        await self._spawn()
        session = await self._conn.new_session(
            cwd=str(self.project_root), mcp_servers=[]
        )
        self._acp_session_id = session.session_id
        await self.send(system_instructions, system=True)

    async def resume(
        self, system_instructions: str, acp_session_id: Optional[str]
    ) -> None:
        """Bring a stored session back to life.

        When the backend supports `session/load` and we have its ACP session id,
        the agent rehydrates its own history (the replayed updates are suppressed,
        since we already hold that transcript). Otherwise we open a fresh session —
        the visible history is preserved but the agent does not remember it — and
        say so.
        """
        await self._spawn()
        if self._supports_load and acp_session_id:
            self._acp_session_id = acp_session_id
            self._suppress_emit = True
            try:
                await self._conn.load_session(
                    cwd=str(self.project_root),
                    session_id=acp_session_id,
                    mcp_servers=[],
                )
            finally:
                self._suppress_emit = False
            self._set_state("idle")
        else:
            session = await self._conn.new_session(
                cwd=str(self.project_root), mcp_servers=[]
            )
            self._acp_session_id = session.session_id
            self._notify(
                "previous agent context could not be restored (backend does not "
                "support session loading); the visible history is preserved but "
                "the agent does not remember it"
            )
            await self.send(system_instructions, system=True)

    async def send(self, text: str, *, system: bool = False) -> None:
        """Run one prompt turn. Rejected (with a notice) while a turn is active."""
        if self._busy:
            self._notify("agent is still responding; wait for the current turn")
            return
        self._busy = True
        self.emit(
            {
                "agent_id": self.agent_id,
                "case_id": self.case_id,
                "type": "message",
                "role": "user",
                "text": text,
                "system": system,
            }
        )
        self._set_state("working")
        try:
            await self._conn.prompt(
                prompt=[text_block(text)],
                session_id=self._acp_session_id,
                message_id=str(uuid.uuid4()),
            )
        except Exception as error:  # surface, don't crash the engine
            self._notify(f"agent error: {error}")
        finally:
            self._busy = False
            self._set_state("idle")

    async def cancel(self) -> None:
        if self._conn is not None and self._acp_session_id is not None:
            await self._conn.cancel(session_id=self._acp_session_id)

    async def stop(self) -> None:
        await self._stack.aclose()

    def _set_state(self, state: str) -> None:
        self.emit(
            {"agent_id": self.agent_id, "case_id": self.case_id,
             "type": "agent_state", "state": state}
        )

    def _notify(self, message: str) -> None:
        self.emit(
            {"agent_id": self.agent_id, "case_id": self.case_id,
             "type": "notice", "message": message}
        )


class SessionManager:
    """Owns all live agent sessions, keyed by agent_id, grouped by case."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def new_agent_id(self) -> str:
        return uuid.uuid4().hex[:8]

    def add(self, session: AgentSession) -> None:
        self._sessions[session.agent_id] = session

    def get(self, agent_id: str) -> Optional[AgentSession]:
        return self._sessions.get(agent_id)

    def pop(self, agent_id: str) -> Optional[AgentSession]:
        return self._sessions.pop(agent_id, None)

    def for_case(self, case_id: str) -> list[AgentSession]:
        return [s for s in self._sessions.values() if s.case_id == case_id]

    def all(self) -> list[AgentSession]:
        return list(self._sessions.values())
