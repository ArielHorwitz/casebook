# Configuration

Casebook is configured with a single TOML file. Everything is optional — with no
config at all, the app runs on the built-in `echo` backend (and the `claude`
backend too, if `claude-code-acp` is on your `PATH`).

## Where the config lives

Casebook reads, in order, merging later over earlier:

1. **Global:** `$XDG_CONFIG_HOME/casebook/config.toml`, or
   `~/.config/casebook/config.toml` if `$XDG_CONFIG_HOME` is unset.
2. **Project override:** `<project-root>/.casebook/config.toml` — handy for
   per-checkout settings. (`.casebook/` is git-ignored by default.)

Merge rules: top-level keys in the project file replace the global ones; the
`[backends.*]` tables are merged **per backend name** (so a project file can add
a backend without redefining the global ones).

## All keys at a glance

| Key | Type | Default | What it does |
|---|---|---|---|
| `default` | string | `"claude"` if available, else `"echo"` | Which backend new sessions use unless one is picked in the UI. |
| `default_model` | string | — | Preferred model, applied at session start when the backend advertises a match (loose match on model id or name). See [backends.md](backends.md#models). |
| `naming_prompt` | string | (built-in) | Instructions handed to the model by the "name session" button. |
| `naming_backend` | string | the session's own backend | Which backend names sessions. `echo` is never used for naming. See [backends.md](backends.md#naming). |
| `naming_model` | string | — | Model to use for naming (same loose match as `default_model`). |
| `[backends.<name>]` | table | echo + claude (built-in) | Define a launchable ACP agent. Full detail: **[backends.md](backends.md)**. |
| `[hotkeys]` | table | (built-in) | Rebind keyboard shortcuts. Full detail: **[hotkeys.md](hotkeys.md)**. |
| `[ui]` | table | `440px`/`320px`/`none` | Session-column sizing — see [UI sizing](#ui-sizing). |

## A complete example

```toml
# ~/.config/casebook/config.toml

default = "claude"
default_model = "sonnet"

# The "name session" button (✨). naming_backend defaults to the session's own
# backend; echo is never used for naming.
naming_prompt = "Reply with a concise title of at most six words for this session."
naming_backend = "claude"
naming_model = "sonnet"

[backends.claude]
command = ["claude-code-acp"]

[backends.gemini]
command = ["gemini", "--experimental-acp"]
env = { GEMINI_API_KEY = "..." }

[hotkeys]
new_session = "n"
focus_next = ["]", "ArrowRight", "ArrowDown"]
```

## UI sizing

Each open session is a column (pane) in the case page's main area. Size them with
a `[ui]` table — values are **CSS lengths**, so any unit works: `vw`/`%` for a
fraction of the screen, `px`/`em`/`rem` for fixed sizes, `none` for no maximum.

| Key | Default | What it does |
|---|---|---|
| `session_width` | `"440px"` | The basis width of each session column. |
| `session_min_width` | `"320px"` | Never shrink a column below this. |
| `session_max_width` | `"none"` | Never grow a column beyond this. |

```toml
[ui]
session_width = "33vw"      # each column is a third of the viewport…
session_min_width = "28em"  # …but at least this wide…
session_max_width = "720px" # …and never wider than this.
```

Columns don't grow or shrink to fit; when they overflow the window the main area
scrolls horizontally.

## See also

- **[backends.md](backends.md)** — what a backend is, the schema, the built-ins,
  worked examples, environment, and how to pin a specific model.
- **[hotkeys.md](hotkeys.md)** — every bindable action, the default keys, and the
  key-name syntax. (The app also lists the *active* bindings live — press `?` or
  click the ⌨ button.)
