# Round-2 feedback: naming model, model granularity, hotkeys

A second batch of feedback after the first implementation pass, plus an explicit
constraint the user reaffirmed.

## Governing constraint (reaffirmed by the user)

> we should only use what's available via the Agent-Client Protocol, and not
> depend on vendor-specific details such as the claude api. if these features are
> not possible, we should note that.

Casebook is a **vendor-agnostic ACP coordinator**. It must rely only on what ACP
exposes (`session/new` → `SessionModelState`, `session/set_model`, `session/prompt`,
etc.), never on a specific vendor's API, model IDs, or CLI internals. Where a
requested feature isn't expressible through ACP, we say so rather than reaching
for vendor specifics. The one place vendor specifics legitimately live is the
**user's own `config.toml`**: a backend is an arbitrary command + env, so a user
can encode vendor-specific launch flags there — casebook itself stays agnostic.

## The three items

### 1. Configurable naming model (echo excluded) — POSSIBLE via ACP

> configurable naming model selection (echo should not be available for this).

Naming runs as an ephemeral one-shot (`engine/oneshot.py`). It is made
configurable through ACP only:

- `naming_backend` and `naming_model` in `config.toml`.
- The one-shot opens an ACP session, and if `naming_model` matches an advertised
  model, applies it via `session/set_model` before prompting — pure ACP.
- Echo is excluded: if the resolved naming backend is `echo` (or none configured
  and the session's own backend is `echo`), naming is unavailable and the user
  gets a notice telling them to set `naming_backend`. Echo has no language model,
  so it can't produce a meaningful name.

### 2. Explicit Claude model granularity (opus 4.8 vs 4.6) — NOT possible via ACP alone

> claude model selection too basic (recommended, sonnet, haiku) cannot select
> opus 4.8 or opus 4.6 explicitly.

The per-session model dropdown is populated **entirely from what the backend
advertises** in ACP's `SessionModelState.available_models`. If the
`claude-code-acp` adapter advertises only coarse buckets (recommended / sonnet /
haiku), then **ACP provides no mechanism to select a finer model** such as
`opus 4.8` vs `opus 4.6` — `session/set_model` can only choose among the
advertised list. Surfacing finer models would require vendor-specific knowledge
(e.g. a Claude-specific env var or CLI flag), which the user explicitly ruled
out at the casebook level.

**Conclusion: this is a backend/adapter limitation, not a casebook one, and it
cannot be fixed through ACP.** What casebook does:

- Surface exactly what the backend advertises (`name`, plus `description` as a
  tooltip) and switch among them via `session/set_model`.
- Provide the vendor-agnostic escape hatch that already exists: define **separate
  backends** in `config.toml`, each launched with that backend's own model-pinning
  flags/env. The user supplies the vendor-specific value; casebook stays agnostic.

  ```toml
  # Example — the model flag/env is the adapter's, not casebook's:
  [backends.claude-opus-48]
  command = ["claude-code-acp"]
  env = { ANTHROPIC_MODEL = "<whatever the adapter honors>" }

  [backends.claude-opus-46]
  command = ["claude-code-acp"]
  env = { ANTHROPIC_MODEL = "<...>" }
  ```

  Then the backend picker selects the pinned model. If/when the adapter advertises
  finer models through ACP, they'll appear in the dropdown automatically with no
  casebook change.

### 3. Configurable hotkeys for everything — POSSIBLE (frontend only, ACP-neutral)

> hotkeys for everything (configurable).

Pure UI; unrelated to ACP. A `[hotkeys]` table in `config.toml` maps actions to
keys (with sensible defaults), served to the browser, which binds them. Shortcuts
are ignored while typing in an input/textarea, and a `?` overlay lists them.
