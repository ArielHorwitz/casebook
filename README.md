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

# Which backend/model the "name session" button uses (optional). Defaults to the
# session's own backend. The built-in `echo` backend is never used for naming.
naming_backend = "claude"
naming_model = "sonnet"

# Preferred model, applied at session start when the backend advertises a match
# (matches a model id or name, case-insensitively). Optional.
default_model = "opus 4.8"

[backends.claude]
command = ["claude-code-acp"]

[backends.gemini]
command = ["gemini", "--experimental-acp"]

# Keyboard shortcuts (optional; any subset overrides the defaults). Press ? in the
# app — or click the ⌨ button — to see the active bindings.
[hotkeys]
new_session = "n"
focus_next = "]"

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

The app is fully keyboard-drivable. `focus next/prev` move between cases on the
home page and between sessions on a case page (same keys); **Enter** opens the
focused case (home) or, on a case page, opens a closed session / focuses the open
session's input box; **Escape** leaves the input box back to navigation. Plus new
case/session, rename/name/close/delete, toggle always-allow, and cancel. Press `?`
or click the ⌨ button to see the bindings; customize them under `[hotkeys]`.

### Model selection

The per-session model dropdown lists exactly the models the backend advertises
over ACP (`session/new` → `availableModels`), and switching uses ACP
`session/set_model`. Casebook is vendor-agnostic, so it cannot offer a model the
backend doesn't expose: if a backend advertises only coarse buckets, that is all
ACP makes selectable. To pin a finer model, define separate backends — each
launched with that backend's own model flags/env — and pick the one you want:

```toml
[backends.assistant-fast]
command = ["some-acp-agent", "--model", "<fast model the agent understands>"]

[backends.assistant-deep]
command = ["some-acp-agent", "--model", "<deep model the agent understands>"]
```

See `docs/casebook/` decision notes for the design choices behind the
implementation.
