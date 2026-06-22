"""Configuration and backend selection.

Casebook reads a single global config at
``$XDG_CONFIG_HOME/casebook/config.toml`` (falling back to
``~/.config/casebook/config.toml``), optionally overlaid by a project-local
``.casebook/config.toml`` for per-checkout overrides. The config declares the
available ACP agent *backends* — a backend is just a command to launch plus
environment — and which one is the default.

Backends are installed explicitly: casebook never fetches one on the fly. Two
backends are built in:

  - ``echo``: a tiny in-tree ACP agent that reflects messages back. Always
    available, so the app is runnable with no setup (useful for development).
  - ``claude``: Zed's ``claude-code-acp`` adapter, but *only* when its binary is
    found on PATH. If you want it, install it (``npm install -g
    @zed-industries/claude-code-acp``); casebook will not run it via npx.

This module is a shared-library candidate (see docs/architecture.md): it knows
nothing about cases.
"""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CLAUDE_ACP_PACKAGE = "@zed-industries/claude-code-acp"
CLAUDE_ACP_BIN = "claude-code-acp"

CONFIG_FILENAME = "config.toml"
PROJECT_CONFIG_RELATIVE_PATH = ".casebook/config.toml"

ECHO_BACKEND_NAME = "echo"
CLAUDE_BACKEND_NAME = "claude"

# The instructions handed to the model when asked to name a session. Override it
# in config.toml with a top-level `naming_prompt = "..."`.
DEFAULT_NAMING_PROMPT = (
    "You are naming a work session based on the transcript that follows. "
    "Reply with a single concise, descriptive title of at most six words. "
    "No surrounding quotes, no trailing punctuation, no preamble — reply with "
    "only the title."
)


# Default keyboard shortcuts (action -> key). Override individually in config.toml
# under a `[hotkeys]` table. Keys are matched against the browser's KeyboardEvent
# `key` value, so e.g. "?" is shift+/ and "]" is the literal bracket.
DEFAULT_HOTKEYS = {
    "new_case": "c",
    "new_session": "n",
    "focus_next": "]",
    "focus_prev": "[",
    "open_focused": "Enter",
    "rename_session": "r",
    "name_session": "g",
    "resume_session": "e",
    "close_session": "x",
    "delete_session": "d",
    "toggle_allow": "a",
    "cancel_turn": "s",
    "help": "?",
}


@dataclass(frozen=True)
class Backend:
    """A launchable ACP agent backend."""

    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


def global_config_dir() -> Path:
    """`$XDG_CONFIG_HOME/casebook`, or `~/.config/casebook` if unset."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home().joinpath(".config")
    return root.joinpath("casebook")


def global_config_path() -> Path:
    return global_config_dir().joinpath(CONFIG_FILENAME)


def echo_backend() -> Backend:
    """The always-available in-tree echo agent (see casebook.echo_backend)."""
    return Backend(
        name=ECHO_BACKEND_NAME,
        command=[sys.executable, "-m", "casebook.echo_backend"],
    )


def builtin_backends() -> dict[str, Backend]:
    """Backends available without any config: echo always, claude if installed."""
    backends = {ECHO_BACKEND_NAME: echo_backend()}
    claude_binary = shutil.which(CLAUDE_ACP_BIN)
    if claude_binary is not None:
        backends[CLAUDE_BACKEND_NAME] = Backend(
            name=CLAUDE_BACKEND_NAME, command=[claude_binary]
        )
    return backends


@dataclass(frozen=True)
class Config:
    """The resolved casebook configuration."""

    backends: dict[str, Backend]
    default_backend: str
    naming_prompt: str = DEFAULT_NAMING_PROMPT
    default_model: Optional[str] = None
    # Which backend/model names sessions. `echo` is never used for naming (it has
    # no language model); when this resolves to echo, naming is unavailable.
    naming_backend: Optional[str] = None
    naming_model: Optional[str] = None
    hotkeys: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))

    def select_backend(self, name: Optional[str] = None) -> Backend:
        chosen = name or self.default_backend
        if chosen not in self.backends:
            available = ", ".join(sorted(self.backends)) or "(none)"
            raise KeyError(f"unknown backend '{chosen}'. Available: {available}")
        return self.backends[chosen]


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def _parse_backends(raw: dict) -> dict[str, Backend]:
    return {
        name: Backend(
            name=name,
            command=list(spec["command"]),
            env=dict(spec.get("env", {})),
        )
        for name, spec in raw.items()
    }


def load_config(project_root: Optional[Path] = None) -> Config:
    """Built-in backends overlaid with global config, then project-local config.

    Config format (``config.toml``):

        default = "claude"

        [backends.claude]
        command = ["claude-code-acp"]

        [backends.gemini]
        command = ["gemini", "--experimental-acp"]
        env = { GEMINI_API_KEY = "..." }
    """
    data = _read_toml(global_config_path())
    if project_root is not None:
        project = _read_toml(project_root.joinpath(PROJECT_CONFIG_RELATIVE_PATH))
        merged_backends = {**data.get("backends", {}), **project.get("backends", {})}
        data = {**data, **project, "backends": merged_backends}

    backends = builtin_backends()
    backends.update(_parse_backends(data.get("backends", {})))

    default = data.get("default")
    if default is None:
        # Prefer a real backend (claude) when present; fall back to echo.
        default = CLAUDE_BACKEND_NAME if CLAUDE_BACKEND_NAME in backends else ECHO_BACKEND_NAME
    return Config(
        backends=backends,
        default_backend=default,
        naming_prompt=data.get("naming_prompt", DEFAULT_NAMING_PROMPT),
        default_model=data.get("default_model"),
        naming_backend=data.get("naming_backend"),
        naming_model=data.get("naming_model"),
        hotkeys={**DEFAULT_HOTKEYS, **data.get("hotkeys", {})},
    )
