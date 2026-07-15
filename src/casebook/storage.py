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
from pathlib import Path

from . import logsetup
from .cases import format_toml_value

log = logsetup.get_logger("storage")

SESSIONS_RELATIVE_PATH = ".casebook/sessions"
META_FILENAME = "meta.toml"
TRANSCRIPT_FILENAME = "transcript.jsonl"


class SessionStore:
    """Reads and writes per-session state under `.casebook/sessions/`."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root.joinpath(SESSIONS_RELATIVE_PATH)

    def _session_dir(self, case_id: str, agent_id: str) -> Path:
        return self.root.joinpath(case_id, agent_id)

    def _ensure_dotdir(self) -> None:
        """Create ``.casebook/`` with a ``.gitignore`` if it doesn't exist."""
        dotdir = self.root.parent  # .casebook/
        gitignore = dotdir.joinpath(".gitignore")
        if not gitignore.exists():
            dotdir.mkdir(parents=True, exist_ok=True)
            gitignore.write_text("*\n")

    def write_meta(self, meta: dict) -> None:
        self._ensure_dotdir()
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

    def rewrite_transcript(self, case_id: str, agent_id: str, events: list[dict]) -> None:
        """Replace the transcript file with the given events (for revert)."""
        session_dir = self._session_dir(case_id, agent_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = session_dir.joinpath(TRANSCRIPT_FILENAME)
        tmp = transcript_path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(event) + "\n" for event in events))
        tmp.replace(transcript_path)

    def load_all_meta(self) -> list[dict]:
        """Every persisted session's metadata, oldest case/agent directory first.

        Only the small ``meta.toml`` is read — never the transcript, which can be
        large and is loaded lazily when a session is actually opened (see
        ``read_transcript``). This keeps startup and reconnection cheap even with
        thousands of stored sessions.
        """
        if not self.root.exists():
            return []
        metas: list[dict] = []
        for case_dir in sorted(self.root.iterdir()):
            if not case_dir.is_dir():
                continue
            for session_dir in sorted(case_dir.iterdir()):
                meta_path = session_dir.joinpath(META_FILENAME)
                if not meta_path.exists():
                    continue
                try:
                    metas.append(tomllib.loads(meta_path.read_text()))
                except (tomllib.TOMLDecodeError, OSError) as error:
                    # Skip a single corrupt session rather than failing startup
                    # (and hiding every other session with it).
                    log.warning("skipping unreadable session meta %s: %s",
                                meta_path, error)
        return metas

    def read_transcript(self, case_id: str, agent_id: str) -> list[dict]:
        """Read one session's transcript from disk (empty if it has none yet)."""
        return _read_transcript(
            self._session_dir(case_id, agent_id).joinpath(TRANSCRIPT_FILENAME)
        )


def _read_transcript(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            # Drop a single truncated/garbled line (e.g. a crash mid-write)
            # rather than losing the whole transcript.
            log.warning("skipping bad transcript line %s:%d: %s", path, number, error)
    return events


def _to_toml(meta: dict) -> str:
    """A flat TOML table; keys whose value is None are omitted (TOML has no null)."""
    lines = [
        f"{key} = {format_toml_value(value)}"
        for key, value in meta.items()
        if value is not None
    ]
    return "\n".join(lines) + "\n"
