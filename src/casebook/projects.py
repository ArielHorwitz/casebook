"""Project path cache for the multi-project home screen.

Casebook tracks which project directories the user has opened, persisted as a
lightweight JSON file at ``~/.config/casebook/projects.json``. Entries are
pruned automatically when their path no longer exists.

A project id is a deterministic short hex hash of the resolved absolute path,
used in URLs (``/project/{id}/``) so paths never appear in the address bar.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import cases, config


CACHE_FILENAME = "projects.json"


def _cache_path() -> Path:
    return config.global_config_dir().joinpath(CACHE_FILENAME)


def project_id(path: Path) -> str:
    """Deterministic 12-char hex id from the resolved absolute path."""
    resolved = str(path.resolve())
    return hashlib.sha256(resolved.encode()).hexdigest()[:12]


def _read_cache() -> list[dict]:
    cache_file = _cache_path()
    if not cache_file.exists():
        return []
    try:
        return json.loads(cache_file.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _write_cache(entries: list[dict]) -> None:
    cache_file = _cache_path()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(entries, indent=2) + "\n")


def _prune(entries: list[dict]) -> list[dict]:
    """Drop entries whose path no longer exists."""
    return [entry for entry in entries if Path(entry["path"]).is_dir()]


def list_projects() -> list[dict]:
    """Return cached projects (pruned), sorted by last_opened descending.

    Each entry: ``{id, path, name, last_opened}``.
    """
    entries = _prune(_read_cache())
    _write_cache(entries)  # persist the pruned version
    entries.sort(key=lambda entry: entry.get("last_opened", ""), reverse=True)
    return entries


def open_project(path: Path) -> dict:
    """Validate and upsert a project path into the cache. Returns the entry."""
    resolved = path.resolve()
    if not resolved.is_dir():
        raise cases.CasebookError(f"directory does not exist: {resolved}")
    pid = project_id(resolved)
    now = datetime.now().isoformat()
    entries = _read_cache()
    for entry in entries:
        if entry["id"] == pid:
            entry["last_opened"] = now
            _write_cache(entries)
            return entry
    entry = {
        "id": pid,
        "path": str(resolved),
        "name": resolved.name,
        "last_opened": now,
    }
    entries.append(entry)
    _write_cache(entries)
    return entry


def resolve_project(pid: str) -> Path:
    """Look up a project id in the cache and return its path."""
    entries = _read_cache()
    for entry in entries:
        if entry["id"] == pid:
            path = Path(entry["path"])
            if not path.is_dir():
                raise cases.CasebookError(
                    f"project directory no longer exists: {entry['path']}"
                )
            return path
    raise cases.CasebookError(f"unknown project: {pid}")


def touch_project(pid: str) -> Optional[dict]:
    """Update last_opened for a project. Returns the entry or None."""
    entries = _read_cache()
    now = datetime.now().isoformat()
    for entry in entries:
        if entry["id"] == pid:
            entry["last_opened"] = now
            _write_cache(entries)
            return entry
    return None
