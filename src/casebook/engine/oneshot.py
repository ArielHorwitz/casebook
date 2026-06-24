"""A one-shot, non-streaming query to a backend.

Used for short utility prompts — naming a session, for example — that should not
touch any live conversation. It spawns its own ephemeral subprocess, sends a
single prompt, collects the agent's message text, and tears the process down. No
events reach the engine bus, and the agent gets no filesystem access (a utility
query has no business writing files).
"""

from __future__ import annotations

import os
import uuid
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Optional

from acp import PROTOCOL_VERSION, RequestPermissionResponse, spawn_agent_process, text_block
from acp.interfaces import Client, ClientCapabilities, Implementation
from acp.schema import DeniedOutcome, FileSystemCapabilities

from ..config import Backend

_NO_FILES = ClientCapabilities(
    fs=FileSystemCapabilities(read_text_file=False, write_text_file=False),
    terminal=False,
)


class _CollectingClient(Client):
    """Collects agent message text; denies everything else."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        if getattr(update, "session_update", None) == "agent_message_chunk":
            content = getattr(update, "content", None)
            self.parts.append(getattr(content, "text", None) or "")

    async def request_permission(self, *args: Any, **kwargs: Any) -> RequestPermissionResponse:
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def read_text_file(self, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError("filesystem unavailable for one-shot queries")

    async def write_text_file(self, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError("filesystem unavailable for one-shot queries")


def _resolve_model(preference: Optional[str], session_response: Any) -> Optional[str]:
    """Match a loose model preference against what this session advertises (ACP)."""
    state = getattr(session_response, "models", None)
    if not preference or state is None:
        return None
    available = getattr(state, "available_models", None) or []
    ids = [model.model_id for model in available]
    if preference in ids:
        return preference
    lowered = preference.lower()
    for model in available:
        if lowered in model.model_id.lower() or lowered in (model.name or "").lower():
            return model.model_id
    return None


async def one_shot(
    backend: Backend,
    project_root: Path,
    prompt: str,
    model: Optional[str] = None,
) -> str:
    """Spawn `backend`, send one prompt, and return the agent's concatenated reply.

    If `model` is given and matches a model the backend advertises, it is selected
    via ACP `session/set_model` before prompting.
    """
    client = _CollectingClient()
    environment = {**os.environ, **backend.env}
    command, *args = backend.command
    async with AsyncExitStack() as stack:
        conn, _process = await stack.enter_async_context(
            spawn_agent_process(
                client,
                command,
                *args,
                cwd=str(project_root),
                env=environment,
                # See session.py for rationale on this limit.
                transport_kwargs={"limit": 100 * 1024 * 1024},
            )
        )
        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=_NO_FILES,
            client_info=Implementation(name="casebook", version="0.1.0"),
        )
        session = await conn.new_session(cwd=str(project_root), mcp_servers=[])
        chosen = _resolve_model(model, session)
        if chosen is not None:
            try:
                await conn.set_session_model(
                    model_id=chosen, session_id=session.session_id
                )
            except Exception:
                pass  # backend may not support set_model; proceed with its default
        await conn.prompt(
            prompt=[text_block(prompt)],
            session_id=session.session_id,
            message_id=str(uuid.uuid4()),
        )
    return "".join(client.parts)
