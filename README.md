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
messages back), so the app always runs even with no model installed.

## Configuration

Casebook reads a single optional TOML file at
`~/.config/casebook/config.toml` (respecting `$XDG_CONFIG_HOME`), optionally
overridden per-project in `.casebook/config.toml`. It configures backends, the
default model, session naming, and keyboard shortcuts:

```toml
default_backend = "claude"

[backends.claude]
command = ["claude-code-acp"]
```

Full reference, with a worked example of every option:

- **[docs/configuration/](docs/configuration/README.md)** — overview and the
  complete key table.
- **[docs/configuration/backends.md](docs/configuration/backends.md)** — defining
  any ACP backend, environment, and pinning a model.
- **[docs/configuration/hotkeys.md](docs/configuration/hotkeys.md)** — every
  bindable action and the key-name syntax.

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

The app's home page (`/`) lists your cases. Each case opens on its **own page**
(`/case/<id>`), so you can keep several cases open in separate browser tabs
alongside the home page — there are no in-app tabs. A case page's sidebar lists
that case's sessions and files; the main area shows the **open** sessions as
side-by-side panes.

Create a case (+ case), open it, and start one or more sessions on it
(+ session) — choosing the backend and, once running, the model. Each session is
its own ACP session, bootstrapped into the case with the casebook directive
inlined as its system instructions — no copy-paste (the directive rides along with
your first message; a new session doesn't speak until you do). Sessions are
persisted: **close** one and it collapses to the sidebar (subprocess stopped,
history kept); **open** it again from the sidebar to resume; **delete** removes it
for good. (When a backend has no native ACP session loading, resume re-sends the
saved transcript as context on your next message and says so.) Sessions working
the same case coordinate through the filesystem, not through each other. Edit
files in your own editor; the app watches the case directory and the agents read
fresh on their next turn.

For one-off queries, the **Scratch** page (linked from the home page) runs
**caseless** sessions — plain agents with no case directive and no files panel. A
scratch session can be **promoted into a new case** (↑ case), migrating the live
session and its history into it.

Every session runs server-side independent of the browser — all sessions in all
cases keep running regardless of which pages are open. The terminal running
`casebook serve` prints when sessions start working and when they all go idle, so
you can check before quitting. Each session pane shows context/token usage (and
cost) when the backend reports it over ACP; session-column width is configurable
(see [docs/configuration/](docs/configuration/README.md#ui-sizing)).

The app is fully keyboard-drivable. `focus next/prev` move between cases on the
home page and between sessions on a case page (same keys); **Enter** opens the
focused case (home) or, on a case page, opens a closed session / focuses the open
session's input box; **Escape** leaves the input box back to navigation. Plus new
case/session, rename/name/close/delete, toggle always-allow, and cancel. Press `?`
or click the ⌨ button to see the bindings; customize them under `[hotkeys]`
(see [docs/configuration/hotkeys.md](docs/configuration/hotkeys.md)).

The per-session model dropdown lists exactly the models the backend advertises
over ACP. Casebook is vendor-agnostic and can't offer a model the backend doesn't
expose — see [docs/configuration/backends.md](docs/configuration/backends.md#models)
for how to pin a specific model.

See `docs/casebook/` decision notes for the design choices behind the
implementation.
