"""Backend configuration and selection.

This is the vendor-agnostic seam: casebook spawns *some* ACP agent subprocess,
and which one is a configuration concern, not a code concern. A backend is just
a command to launch plus environment. The default is Claude via Zed's
`claude-code-acp` adapter, but anything that speaks ACP over stdio works.

Resolution order for the default Claude backend's command:
  1. an explicit `command` in `.casebook/backends.toml`
  2. a `claude-code-acp` binary on PATH
  3. `npx -y @zed-industries/claude-code-acp` (no install needed)

This module is a shared-library candidate (see docs/architecture.md): it knows
nothing about cases.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CLAUDE_ACP_PACKAGE = "@zed-industries/claude-code-acp"
CLAUDE_ACP_BIN = "claude-code-acp"
CONFIG_RELATIVE_PATH = ".casebook/backends.toml"


@dataclass(frozen=True)
class Backend:
    """A launchable ACP agent backend."""

    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


def _default_claude_command() -> list[str]:
    binary = shutil.which(CLAUDE_ACP_BIN)
    if binary is not None:
        return [binary]
    if shutil.which("npx") is not None:
        return ["npx", "-y", CLAUDE_ACP_PACKAGE]
    raise FileNotFoundError(
        f"could not find '{CLAUDE_ACP_BIN}' on PATH and 'npx' is unavailable. "
        f"Install it with: npm install -g {CLAUDE_ACP_PACKAGE}"
    )


def builtin_backends() -> dict[str, Backend]:
    return {"claude": Backend(name="claude", command=_default_claude_command())}


def load_backends(project_root: Path) -> dict[str, Backend]:
    """Built-in backends overlaid with any defined in `.casebook/backends.toml`.

    Config format:

        default = "claude"

        [backends.claude]
        command = ["claude-code-acp"]

        [backends.gemini]
        command = ["gemini", "--experimental-acp"]
        env = { GEMINI_API_KEY = "..." }
    """
    backends = builtin_backends()
    config_path = project_root.joinpath(CONFIG_RELATIVE_PATH)
    if config_path.exists():
        config = tomllib.loads(config_path.read_text())
        for name, spec in config.get("backends", {}).items():
            backends[name] = Backend(
                name=name,
                command=list(spec["command"]),
                env=dict(spec.get("env", {})),
            )
    return backends


def select_backend(project_root: Path, name: Optional[str] = None) -> Backend:
    backends = load_backends(project_root)
    if name is None:
        config_path = project_root.joinpath(CONFIG_RELATIVE_PATH)
        if config_path.exists():
            name = tomllib.loads(config_path.read_text()).get("default")
        name = name or "claude"
    if name not in backends:
        available = ", ".join(sorted(backends)) or "(none)"
        raise KeyError(f"unknown backend '{name}'. Available: {available}")
    return backends[name]
