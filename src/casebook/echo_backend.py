"""A minimal, built-in ACP agent that echoes user messages back.

This is the always-available fallback backend (see config.py). It speaks ACP over
stdio like any real backend, so casebook is runnable and developable without a
model installed. It has no memory and does not support session loading — it
simply reflects each prompt's text back as an agent message.

Run as ``python -m casebook.echo_backend``; that is exactly the command the
built-in ``echo`` backend launches.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from acp import PROTOCOL_VERSION, AgentSideConnection, stdio_streams, text_block
from acp.interfaces import Implementation
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    InitializeResponse,
    ModelInfo,
    NewSessionResponse,
    PromptResponse,
    SessionModelState,
    SetSessionModelResponse,
)

# Two pretend models, so model selection is demonstrable without a real backend.
_MODELS = [
    ModelInfo(model_id="echo-small", name="Echo Small"),
    ModelInfo(model_id="echo-large", name="Echo Large"),
]


class EchoAgent:
    """An ACP agent whose every reply is the prompt text, prefixed with `echo:`."""

    def __init__(self, connection: AgentSideConnection) -> None:
        self._connection = connection
        self._model_by_session: dict[str, str] = {}

    async def initialize(self, protocol_version: int, **kwargs: Any) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(load_session=False),
            agent_info=Implementation(name="echo", version="0.1.0"),
        )

    async def new_session(self, cwd: str, **kwargs: Any) -> NewSessionResponse:
        session_id = f"echo-{uuid.uuid4().hex}"
        self._model_by_session[session_id] = _MODELS[0].model_id
        return NewSessionResponse(
            session_id=session_id,
            models=SessionModelState(
                available_models=_MODELS, current_model_id=_MODELS[0].model_id
            ),
        )

    async def set_session_model(
        self, model_id: str, session_id: str, **kwargs: Any
    ) -> SetSessionModelResponse:
        self._model_by_session[session_id] = model_id
        return SetSessionModelResponse()

    async def prompt(self, prompt: list, session_id: str, **kwargs: Any) -> PromptResponse:
        text = "".join(getattr(block, "text", "") for block in prompt)
        model = self._model_by_session.get(session_id, _MODELS[0].model_id)
        await self._connection.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                content=text_block(f"echo[{model}]: {text}"),
                session_update="agent_message_chunk",
            ),
        )
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        return None


async def _main() -> None:
    reader, writer = await stdio_streams()
    connection = AgentSideConnection(
        lambda conn: EchoAgent(conn),
        writer,
        reader,
        listening=False,
        use_unstable_protocol=True,
    )
    await connection.listen()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
