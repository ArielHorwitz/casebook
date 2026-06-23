"""On-disk persistence for agent sessions.

Sessions live under ``<project_root>/.casebook/sessions/<case_id>/<agent_id>/`` as
a ``meta.toml`` (the session's identity and resume info) plus a
``transcript.jsonl`` (the append-only replayable event log). This is local
checkout state — ``.casebook/`` is git-ignored — not case content: a case's
durable artifacts are the files agents write, which remain the source of truth.
Persisting sessions just lets the app restore the list of past sessions and
resume them after a restart.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .cases import format_toml_value

SESSIONS_RELATIVE_PATH = ".casebook/sessions"
META_FILENAME = "meta.toml"
TRANSCRIPT_FILENAME = "transcript.jsonl"


@dataclass
class StoredSession:
    """A session loaded from disk: its metadata and its replayed transcript."""

    meta: dict
    transcript: list[dict] = field(default_factory=list)


class SessionStore:
    """Reads and writes per-session state under `.casebook/sessions/`."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root.joinpath(SESSIONS_RELATIVE_PATH)

    def _session_dir(self, case_id: str, agent_id: str) -> Path:
        return self.root.joinpath(case_id, agent_id)

    def write_meta(self, meta: dict) -> None:
        session_dir = self._session_dir(meta["case_id"], meta["agent_id"])
        session_dir.mkdir(parents=True, exist_ok=True)
        session_dir.joinpath(META_FILENAME).write_text(_to_toml(meta))

    def append_event(self, case_id: str, agent_id: str, event: dict) -> None:
        session_dir = self._session_dir(case_id, agent_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        with session_dir.joinpath(TRANSCRIPT_FILENAME).open("a") as file:
            file.write(json.dumps(event) + "\n")

    def delete(self, case_id: str, agent_id: str) -> None:
        session_dir = self._session_dir(case_id, agent_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def relocate(self, old_case_id: str, new_case_id: str, agent_id: str) -> None:
        """Move a session's on-disk directory from one case to another."""
        old = self._session_dir(old_case_id, agent_id)
        new = self._session_dir(new_case_id, agent_id)
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))

    def load_all(self) -> list[StoredSession]:
        """Every persisted session, oldest case/agent directory first."""
        if not self.root.exists():
            return []
        sessions: list[StoredSession] = []
        for case_dir in sorted(self.root.iterdir()):
            if not case_dir.is_dir():
                continue
            for session_dir in sorted(case_dir.iterdir()):
                meta_path = session_dir.joinpath(META_FILENAME)
                if not meta_path.exists():
                    continue
                sessions.append(
                    StoredSession(
                        meta=tomllib.loads(meta_path.read_text()),
                        transcript=_read_transcript(
                            session_dir.joinpath(TRANSCRIPT_FILENAME)
                        ),
                    )
                )
        return sessions


def _read_transcript(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def _to_toml(meta: dict) -> str:
    """A flat TOML table; keys whose value is None are omitted (TOML has no null)."""
    lines = [
        f"{key} = {format_toml_value(value)}"
        for key, value in meta.items()
        if value is not None
    ]
    return "\n".join(lines) + "\n"
