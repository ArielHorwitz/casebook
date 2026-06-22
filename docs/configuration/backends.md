# Backends

A **backend** is the agent casebook launches for a session. Casebook is
vendor-agnostic: a backend is just *a command to run* (plus optional environment)
that speaks the [Agent Client Protocol](https://agentclientprotocol.com) (ACP)
over stdio. Any ACP-speaking agent works; casebook knows nothing about which
vendor or model is behind it.

## How a backend runs

When you start a session on a backend, casebook:

1. launches the backend's `command` as a subprocess, with the **project root** as
   its working directory;
2. gives it the **full inherited environment**, overlaid with the backend's `env`;
3. speaks ACP to it over stdin/stdout (initialize → new session → prompts).

Because the agent is your own trusted tool, it gets your real environment (PATH,
ambient credentials, etc.), not a trimmed one.

## Schema

Each backend is a table under `[backends.<name>]`. `<name>` is what you'll see in
the backend picker and can set as `default`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `command` | array of strings | yes | The program and its arguments, e.g. `["claude-code-acp"]` or `["gemini", "--experimental-acp"]`. The first element is resolved on `PATH`. |
| `env` | table of strings | no | Extra environment variables for the subprocess, overlaid on the inherited environment. |

```toml
[backends.example]
command = ["my-acp-agent", "--flag", "value"]
env = { MY_API_KEY = "sk-...", MY_REGION = "eu" }
```

## Built-in backends

These exist without any config:

- **`echo`** — a tiny in-tree ACP agent (`python -m casebook.echo_backend`) that
  reflects your messages back. Always available, so the app runs with no setup;
  useful for development. It has no language model (see [Naming](#naming)).
- **`claude`** — Zed's `claude-code-acp` adapter, **but only if its binary is
  found on `PATH`**. Casebook will not fetch or run it via `npx` — install it
  explicitly (`npm install -g @zed-industries/claude-code-acp`) and it appears
  automatically.

Anything you declare under `[backends.*]` is added to these (and overrides a
built-in of the same name).

## Choosing the default

`default` selects the backend new sessions use unless you pick another in the UI.
If you don't set it, casebook uses `claude` when available, otherwise `echo`.

```toml
default = "gemini"
```

## Worked examples

```toml
# Claude via Zed's adapter (explicit path or just the name if it's on PATH)
[backends.claude]
command = ["claude-code-acp"]

# Gemini's experimental ACP mode, with an API key
[backends.gemini]
command = ["gemini", "--experimental-acp"]
env = { GEMINI_API_KEY = "..." }

# Run an adapter through npx if you prefer (a deliberate choice, not a fallback)
[backends.claude-npx]
command = ["npx", "-y", "@zed-industries/claude-code-acp"]

# Any other ACP agent on your machine
[backends.custom]
command = ["/opt/agents/my-agent", "serve", "--acp"]
env = { MY_AGENT_TOKEN = "..." }
```

## Models

Once a session is running, the model dropdown lists exactly the models the backend
**advertises over ACP** (`session/new` → `availableModels`); switching uses ACP
`session/set_model`. `default_model` (in the top-level config) is applied at
session start when the backend advertises a matching model (matched
case-insensitively against the model's id or name).

Casebook cannot offer a model the backend doesn't expose. If a backend only
advertises coarse buckets, that's all ACP makes selectable. To pin a *specific*
model, define **separate backends**, each launched with that backend's own
model-selection flags or env — the vendor-specific value lives in your config, and
casebook stays agnostic:

```toml
[backends.assistant-fast]
command = ["some-acp-agent", "--model", "<fast model the agent understands>"]

[backends.assistant-deep]
command = ["some-acp-agent", "--model", "<deep model the agent understands>"]
```

Then pick the backend you want from the picker (or set `default`).

## Naming {#naming}

The "name session" button runs a short one-shot query on `naming_backend` (or the
session's own backend if unset), optionally pinned to `naming_model`. The built-in
`echo` backend is **never** used for naming — it has no language model — so if
naming would resolve to `echo`, the app tells you to set `naming_backend`.

## Verifying

Start `casebook serve` and open a case: configured backends appear in the
**+ session** backend picker. If a backend fails to launch, the failure surfaces
as a toast/notice (e.g. a wrong command or missing binary).
