# Round-6 feedback: configuration is underdocumented

> what is available and possible in the config is unclear … i'm thinking we
> should have a separate document for each of these in detail.

The README only showed a couple of backend/hotkey snippets, so it wasn't obvious
what else could be set or how. Added a dedicated, detailed configuration reference
under **`docs/configuration/`**:

- `README.md` — config file locations + merge precedence (global
  `~/.config/casebook/config.toml`, project `.casebook/config.toml`), and a single
  table of **every** top-level key (`default`, `default_model`, `naming_prompt`,
  `naming_backend`, `naming_model`, `[backends.*]`, `[hotkeys]`) with defaults.
- `backends.md` — what a backend is (an ACP command + env), the schema, the
  built-ins (`echo`, and `claude` when on PATH), worked examples (claude, gemini,
  npx, custom), the environment/cwd behaviour, model selection, and the
  multi-backend model-pinning pattern.
- `hotkeys.md` — every bindable action with its default key(s) and context, the
  always-on keys (Enter/Shift+Enter/Escape), and the `KeyboardEvent.key` naming
  syntax (case sensitivity, named keys, no modifier combos, no firing while
  typing).

The README's configuration section was trimmed to a short example plus links to
these docs (and a stale unclosed TOML fence in the README was fixed). The in-app
`?` overlay remains the live source of the *active* hotkey bindings.
