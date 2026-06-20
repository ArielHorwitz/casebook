# casebook

A coordinator that connects your filesystem **casebook** (a per-project
collection of cases — bounded units of work) to configurable **ACP agent
backends**, so you can work a case start-to-finish in one surface instead of
copy-pasting a preamble between your editor and a separate agent UI.

The filesystem is the source of truth. Casebook reflects it; it never becomes a
competing store of state. See `docs/vision.md` for intent and
`docs/architecture.md` for the cross-app design.

## Install

```bash
uv pip install -e .
# Backends are installed explicitly. The Claude backend uses Zed's adapter and
# is picked up automatically once its binary is on PATH:
npm install -g @zed-industries/claude-code-acp   # optional
```

Casebook ships a built-in `echo` backend (an in-tree ACP agent that reflects
messages back), so the app always runs even with no model installed. Configure
additional backends in `~/.config/casebook/config.toml` (respecting
`$XDG_CONFIG_HOME`), optionally overridden per-project in `.casebook/config.toml`:

```toml
default = "claude"

# Instructions used by the "name session" button (optional; shown is the default).
naming_prompt = "Reply with a concise title of at most six words for this session."

[backends.claude]
command = ["claude-code-acp"]

[backends.gemini]
command = ["gemini", "--experimental-acp"]
```

## CLI

```bash
casebook init                 # initialize docs/casebook/ in a project
casebook new -t "Title"       # create a case
casebook list                 # list cases
casebook show <id>            # show a case
casebook serve                # launch the coordinator app (browser UI)
```

`casebook serve` then prints a local URL (default http://127.0.0.1:8765).

## App

The app opens on your cases. Pick one, add one or more agents to it, and
converse. Each agent is its own ACP session, bootstrapped into the case with the
casebook directive inlined as its system instructions — no copy-paste. Agents
working the same case coordinate through the filesystem, not through each other.
Edit files in your own editor; the app watches the case directory and the agents
read fresh on their next turn.

See `docs/casebook/` decision notes for the design choices behind the
implementation.
