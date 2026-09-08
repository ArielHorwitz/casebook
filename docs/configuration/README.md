# Configuration

FalconFox reads one daemon-global TOML file:
`$XDG_CONFIG_HOME/falconfox/config.toml`, or
`~/.config/falconfox/config.toml` when `$XDG_CONFIG_HOME` is unset.
There are no per-working-directory overrides: a session's `path` is metadata,
not a configuration scope.

Everything is optional. With no file, the built-in `echo` ACP backend is used.

```toml
default_backend = "codex"
naming_backend = "codex"
naming_prompt = "Reply with a concise title of at most six words."
log_level = "INFO"

[backends.codex]
command = ["codex-acp"]
env = { OPTIONAL_BACKEND_VALUE = "..." }

[backends.codex.config_options]
model = "gpt-5.5"
reasoning_effort = "high"

# Telegram topic icons, one per session tag. No default: uncomment and use
# your own vocabulary, since FalconFox attaches no meaning to a tag.
# [telegram.topic_icons]
# archived = "📁"
# urgent = "❗️"
# review = "👀"
```

| Key | Default | Purpose |
|---|---|---|
| `default_backend` | first declared backend, else `echo` | Backend used by `spawn` unless `--backend` is supplied. |
| `naming_backend` | unset | Backend used by automatic session naming. |
| `naming_prompt` | built in | Prompt for automatic session naming. |
| `log_level` | `INFO` | Daemon logging level; `FALCONFOX_LOG_LEVEL` overrides it. |
| `[backends.<name>]` | `echo` only | ACP subprocess command, environment, and config-option defaults. |
| `[telegram.topic_icons]` | unset | Maps a session tag to the forum topic icon drawn for it. |

## Topic icons

A session can carry tags (`falconfox tag <id> <tags...>`), which are opaque
labels: FalconFox stores them, lists them and nothing else. `[telegram.topic_icons]`
is where they acquire a visible meaning, by naming an icon per tag.

Values are written as the emoji itself. Telegram allows only a fixed set as
topic icons, resolved at bot startup from `getForumTopicIconStickers`; an
emoji outside that set is skipped with a warning in the log, and a raw
custom-emoji id is passed through for anything the endpoint does not list.

A topic has one icon slot but a session may have several tags, so the **first
tag with an icon wins**, in the order the tags were set. Tags without an icon
fall through, and a session whose tags map to nothing keeps the plain
coloured icon it was created with.


The retained `[hotkeys]` and `[ui]` settings belong to the browser pane code.
That UI is intentionally unwired in the local PoC and will be documented again
when the flat session navigation is rebuilt.

See [backends.md](backends.md) for backend setup and config-option behavior.
