"""The case model: discovery, metadata, and paths.

The filesystem is the source of truth. Nothing here caches state; every call
reflects what is on disk right now. This module is deliberately free of any
agent/ACP knowledge — it is the domain layer both the CLI and the app read.
"""

from __future__ import annotations

import datetime
import secrets
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import templates

CASEBOOK_DIR = "docs/casebook"


class CasebookError(Exception):
    """Raised for expected, user-facing failures (no casebook, bad case id...)."""


def find_project_root(start: Optional[Path] = None) -> Path:
    """Walk upward from `start` (cwd by default) to the nearest casebook root."""
    current = (start or Path.cwd()).resolve()
    while True:
        if current.joinpath(CASEBOOK_DIR).is_dir():
            return current
        if current.parent == current:
            raise CasebookError(f"no casebook found (looking for {CASEBOOK_DIR}/)")
        current = current.parent


def find_casebook_root(start: Optional[Path] = None) -> Path:
    return find_project_root(start).joinpath(CASEBOOK_DIR)


def new_case_id() -> str:
    date_prefix = datetime.date.today().strftime("%Y-%m-%d")
    return f"{date_prefix}__{secrets.token_hex(4)}"


def format_toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "[" + ", ".join(format_toml_value(item) for item in value) + "]"
    return str(value)


@dataclass(frozen=True)
class Case:
    """A single case, resolved to its directory on disk."""

    path: Path
    metadata: dict

    @property
    def case_id(self) -> str:
        return self.path.name

    @property
    def title(self) -> str:
        return self.metadata.get("title", "(untitled)")

    @property
    def status(self) -> str:
        return self.metadata.get("status", "unknown")

    @property
    def keywords(self) -> list:
        return self.metadata.get("keywords", [])

    @property
    def hidden(self) -> bool:
        return self.path.joinpath(".gitignore").exists()

    def files(self) -> list[str]:
        """Case files the user/agent works with (metadata and tool dotfiles hidden)."""
        return sorted(
            entry.name
            for entry in self.path.iterdir()
            if entry.is_file()
            and entry.name != "case.toml"
            and not entry.name.startswith(".")
        )


def load_case_metadata(case_path: Path) -> dict:
    toml_path = case_path.joinpath("case.toml")
    if not toml_path.exists():
        return {}
    return tomllib.loads(toml_path.read_text())


def load_case(case_path: Path) -> Case:
    return Case(path=case_path, metadata=load_case_metadata(case_path))


def iter_case_dirs(casebook_path: Path):
    return sorted(
        entry
        for entry in casebook_path.iterdir()
        if entry.is_dir() and entry.joinpath("case.toml").exists()
    )


def list_cases(
    casebook_path: Path,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
) -> list[Case]:
    cases = [load_case(path) for path in iter_case_dirs(casebook_path)]
    if status is not None:
        cases = [case for case in cases if case.status == status]
    if keyword is not None:
        cases = [case for case in cases if keyword in case.keywords]
    return cases


def resolve_case(casebook_path: Path, case_id: str) -> Case:
    """Resolve a full directory name or a hex-id prefix to a single case."""
    matches = [
        path
        for path in casebook_path.iterdir()
        if path.is_dir()
        and (path.name == case_id or path.name.split("__", 1)[-1].startswith(case_id))
    ]
    if not matches:
        raise CasebookError(f"no case matching '{case_id}'")
    if len(matches) > 1:
        names = ", ".join(sorted(path.name for path in matches))
        raise CasebookError(f"ambiguous case id '{case_id}', matches: {names}")
    return load_case(matches[0])


def create_case(casebook_path: Path, title: str) -> Case:
    """Create a new case directory with metadata.

    No content files are written: the user is encouraged to add an overview (and
    any intro/design docs) themselves, but nothing is required up front.
    """
    case_id = new_case_id()
    case_path = casebook_path.joinpath(case_id)
    case_path.mkdir(parents=True)
    case_path.joinpath("case.toml").write_text(
        templates.CASE_TOML_TEMPLATE.format(
            title=format_toml_value(title or "Unnamed case"),
            created=format_toml_value(datetime.datetime.now().isoformat()),
        )
    )
    return load_case(case_path)
