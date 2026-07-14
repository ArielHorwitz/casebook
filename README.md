# casebook

Casebook is a browser-based app for working with AI agents on structured units
of work called **cases**.

## Concepts

A **casebook** is a directory of cases in your project (by default
`docs/casebook/`). Each **case** is a subdirectory containing a metadata file
(`case.toml`), an overview (`overview.md`), and whatever other files the work
produces — analysis, designs, reports, code plans, etc. The filesystem is the
source of truth; casebook reflects it.

A **session** is a conversation with an agent, tied to a case. The agent
automatically picks up the case's context — its directive, files, and related
cases — so it's oriented from the start. Multiple sessions can work the same
case in parallel; they coordinate through the filesystem, not through each
other.

A **backend** is any command that speaks the
[Agent Client Protocol](https://agentclientprotocol.com) (ACP) over stdio.
Casebook is vendor-agnostic — it doesn't know or care which model or vendor is
behind a backend. You configure backends in a TOML file; casebook launches them
as subprocesses and talks ACP to them. See
[docs/configuration/backends.md](docs/configuration/backends.md) for the full
reference.

## Getting started

### Install casebook

```bash
uv tool install git+https://github.com/ArielHorwitz/casebook
```

Or for development:

```bash
git clone https://github.com/ArielHorwitz/casebook
cd casebook
uv pip install -e .
```

### Install a backend

Casebook ships a built-in `echo` backend (reflects your messages back) so the
app always runs, but you'll want a real agent. The most common backend is
Claude via the `claude-agent-acp` adapter:

```bash
npm install -g @agentclientprotocol/claude-agent-acp
```

Once `claude-agent-acp` is on your `PATH`, casebook detects it automatically —
no configuration needed. It uses your ambient Anthropic credentials.

For other backends (Gemini, custom agents, etc.), see
[docs/configuration/backends.md](docs/configuration/backends.md).

### Run casebook

```bash
casebook                      # start daemon + open browser
casebook /path/to/project     # open browser to a specific project
casebook --fg                 # foreground server + open browser
casebook --fg --no-browser    # foreground server, no browser
casebook --stop               # stop running daemon
```

The `casebook` command auto-starts a background daemon if one isn't already
running, then opens your browser to the UI.

## Using the app

The **home page** lists your cases. Each case opens on its own page, so you can
keep several cases open in separate browser tabs.

On a **case page**, the sidebar lists that case's sessions and files; the main
area shows open sessions as side-by-side panes. Create a session with
**+ session**, pick a backend, and start talking. Each session pane shows the
conversation, tool-call activity, permission prompts, and context/token usage
when the backend reports it.

For one-off queries without a case, the **Scratch** page runs caseless
sessions — plain agents with no case directive. A scratch session can be
promoted into a new case, migrating its history.

All sessions run server-side, independent of the browser — they keep running
regardless of which pages are open.

### Keyboard navigation

The app is fully keyboard-drivable. Press `?` or click the **&#x2328;** button to
see the active bindings. Customize them under `[hotkeys]` in your config (see
[docs/configuration/hotkeys.md](docs/configuration/hotkeys.md)).

## Configuration

Casebook reads a single optional TOML file at
`~/.config/casebook/config.toml` (respects `$XDG_CONFIG_HOME`), optionally
overridden per-project in `.casebook/config.toml`.

```toml
default_backend = "claude"

[backends.claude]
command = ["claude-agent-acp"]
default_model = "sonnet"

[backends.gemini]
command = ["gemini", "--experimental-acp"]
default_model = "gemini-2.5-pro"
env = { GEMINI_API_KEY = "..." }
```

Full reference:

- **[Configuration overview](docs/configuration/README.md)** — all keys, merge
  rules, and a complete example.
- **[Backends](docs/configuration/backends.md)** — defining backends, the
  built-ins, environment, models, and worked examples.
- **[Hotkeys](docs/configuration/hotkeys.md)** — every bindable action, defaults,
  and key-name syntax.
