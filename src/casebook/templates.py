"""Static text templates owned by the tool.

Kept apart from logic so the directive wording is easy to find and edit.
"""

AGENTS_MD = """\
# Casebook

You have been assigned to a **case** — a bounded unit of work (investigation,
brainstorm, feature, design, etc.) with its own directory under `docs/casebook/`.

## Your case directory

Each case directory contains:

- **`case.toml`** — metadata that casebook uses for listing and discovery.
  Keep its fields current as the work evolves:
  - `title`: the primary way cases are discovered. It should capture the full
    scope — anyone searching for this case should be able to find it by title.
    New cases default to "Unnamed case"; rename early and refine as scope
    becomes clearer.
  - `status`: any value is valid — typically `open` or `closed`, but
    freeform values like `blocked` or `paused` work too.
  - `keywords`: keep updated to help future sessions find relevant cases.
- **`overview.md`** — a living summary of the case. Create it early and keep it
  current so future sessions can quickly load context.
- **Other files** — analysis, reports, decisions, designs, etc. Use highly
  descriptive filenames so that a reader can understand what a file contains
  from its name alone (e.g. `websocket-reconnection-backoff-strategy.md`, not
  `notes.md`).

Code belongs in the source tree, not in the case directory.

## The broader casebook

Your case is one of many under `docs/casebook/`. Other case directories may
hold useful historical context — prior investigations, design decisions, or
previously considered approaches. You can browse them when relevant, but
usually everything you need is in your own case.
"""

CASEBOOK_README = """\
This directory is managed by `casebook` and its agents.
"""


def system_instructions(case_id: str) -> str:
    """An agent's bootstrap turn: the full directive plus its case assignment.

    ACP has no separate system-prompt channel, so casebook sends this as the first
    turn of each session bound to a case. The directive is inlined directly rather
    than pointing the agent at a file to read — no extra round-trip, no preamble.
    When several agents share a case they each receive it, then coordinate through
    the filesystem rather than through each other.
    """
    return (
        f"{AGENTS_MD}\n"
        f"You are working on case `{case_id}` (under `docs/casebook/`). Read its "
        f"files to load context.\n"
    )

CASE_TOML_TEMPLATE = """\
title = {title}
status = "open"
created = {created}
keywords = []
"""
