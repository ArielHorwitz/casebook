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
# the Claude backend uses Zed's adapter, resolved from PATH or npx:
npm install -g @zed-industries/claude-code-acp   # optional; npx is used otherwise
```

## CLI

```bash
casebook init                 # initialize docs/casebook/ in a project
casebook new -t "Title"       # create a case (opens $EDITOR for the intro)
casebook list                 # list cases
casebook show <id>            # show a case
casebook serve                # launch the coordinator app (browser UI)
```

`casebook serve` then prints a local URL (default http://127.0.0.1:8765).

## App

The app opens on your cases. Pick one, add one or more agents to it, and
converse. Each agent is its own ACP session, bootstrapped into the case with the
preamble automatically — no copy-paste. Agents working the same case coordinate
through the filesystem, not through each other. Edit files in your own editor;
the app watches the case directory and the agents read fresh on their next turn.

See `docs/casebook/` decision notes for the design choices behind the
implementation.
