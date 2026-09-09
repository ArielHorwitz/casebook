"""Help modules: nested markdown that a client registers for agents to read.

Orientation is what a session cannot work without and is told once, unasked.
This is the other half: what it can look up when it turns out to matter, at
the cost of a turn. The split is why orientation can stay short while the
detail behind it grows without bound.

The layout mirrors the one orientation already uses, in the same per-run
directory, so registering both is one write:

    <run>/help/<name>.md                    -> .<name>
    <run>/clients/<client>/help/<name>.md   -> <client>.<name>
    <run>/clients/<client>/help/<a>/<b>.md  -> <client>.<a>.<b>

The empty namespace is the daemon's own, exactly as it is for roles, so
`.lifecycle` reads the same way `.manager` does. A client's namespace is its
directory name, so nothing has to trust a name a client wrote for itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

HELP_DIRNAME = "help"


def _title(body: str) -> str:
    """The first heading, or failing that the first line with anything on it.

    No frontmatter: a title block is a second place for the name of a document
    to live, and the two drift. The heading a reader already sees is the one
    the listing shows.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            return stripped
    return ""


def discover(run_dir: Path) -> dict[str, Path]:
    """Every registered module this run, keyed by its dotted path."""
    sources: list[tuple[str, Path]] = [("", run_dir.joinpath(HELP_DIRNAME))]
    clients = run_dir.joinpath("clients")
    if clients.is_dir():
        sources += [(client.name, client.joinpath(HELP_DIRNAME))
                    for client in sorted(clients.iterdir()) if client.is_dir()]
    found: dict[str, Path] = {}
    for namespace, root in sources:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            parts = path.relative_to(root).with_suffix("").parts
            found[namespace + "." + ".".join(parts)] = path
    return found


def read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def index(run_dir: Path, prefix: Optional[str] = None) -> str:
    """The listing: one dotted path per line, with its title.

    The whole tree rather than one level at a time. The reader is usually an
    agent, and for an agent a longer listing beats a second turn spent
    descending into it.
    """
    entries = discover(run_dir)
    if prefix:
        entries = {name: path for name, path in entries.items()
                   if name == prefix or name.startswith(prefix + ".")}
    if not entries:
        return ""
    width = max(len(name) for name in entries)
    return "\n".join(f"{name.ljust(width)}  {_title(read(path))}"
                     for name, path in sorted(entries.items()))


def lookup(run_dir: Path, name: str) -> Optional[str]:
    """A module's text, or a listing when the name is a branch rather than a
    leaf. Returns None when it is neither.

    A name can be both -- `telegram.commands` beside `telegram.commands.new` --
    and the module wins, with a pointer to what is underneath it. Listing
    instead would hide a document behind its own children.
    """
    entries = discover(run_dir)
    path = entries.get(name)
    if path is not None:
        body = read(path)
        below = index(run_dir, name)
        deeper = "\n".join(line for line in below.splitlines()
                           if not line.startswith(name + " ")
                           and not line.startswith(name + "  "))
        return f"{body}\n\nMore under this topic:\n{deeper}" if deeper else body
    listing = index(run_dir, name)
    return listing or None
