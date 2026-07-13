# Handoff: Backends guide, config reload, and per-backend default model

This replaces the original backend-installation and settings-page handoffs.
The in-app registry, settings UI, and config-writing infrastructure were
prototyped and scrapped — the complexity wasn't justified for the user base.
Configuration stays file-only (`config.toml`).

## What needs doing

Three things, in rough priority order. Items 1 and 2 are implemented; item 3
remains.

### 1. Per-backend `default_model` — IMPLEMENTED

**Problem:** There's a single top-level `default_model` in the config, but model
IDs are backend-specific. Setting `default_model = "sonnet"` is meaningless for
a Gemini backend.

**Change:** Move `default_model` into the backend table.

```toml
[backends.claude]
command = ["claude-code-acp"]
default_model = "sonnet"

[backends.gemini]
command = ["gemini", "--experimental-acp"]
default_model = "gemini-2.5-pro"
env = { GEMINI_API_KEY = "..." }
```

The top-level `default_model` key should be removed entirely.

**Files to modify:**

- `src/casebook/config.py`:
  - Add `default_model: Optional[str] = None` to the `Backend` dataclass.
  - Remove `default_model` from the `Config` dataclass.
  - Update `_parse_backends()` to read `default_model` from each backend's spec.
  - Update `load_config()` to stop reading the top-level `default_model`.

- `src/casebook/coordinator.py`:
  - `_apply_models()` (line ~529): reads `self.config.default_model` — change to
    read from the backend: `backend.default_model` where `backend` is the
    `Backend` instance for the session. The `Backend` is available via
    `self.config.select_backend(agent["backend"])`.

- `docs/configuration/README.md`:
  - Remove `default_model` from the "All keys at a glance" table.
  - Update the complete example to show `default_model` inside backend tables.

- `docs/configuration/backends.md`:
  - Add `default_model` to the backend schema table.
  - Update the "Models" section to explain per-backend `default_model` as the
    simple case, with separate-backends-per-model as the advanced case.
  - Update worked examples.

- `README.md`:
  - Update the configuration snippet if it mentions `default_model`.

Also update naming: `naming_backend` + `naming_model` stay as top-level keys
(they select *which backend to use for naming* and *which model on that backend*,
which is a different concern from the session's own default model). No change
needed there.

### 2. Config hot-reload — IMPLEMENTED

**Problem:** Config is read once at startup by `CaseCoordinator.__init__`. If a
user edits `config.toml`, they have to restart the daemon.

**Change:**

- `src/casebook/coordinator.py`: Add a `reload_config()` method:
  ```python
  def reload_config(self) -> None:
      self.config = config.load_config(self.project_root)
      self._emit({"type": "config_changed"})
  ```
  New sessions after reload use the new config. Existing live sessions keep their
  current backend/model (they're already running).

- `src/casebook/web/server.py`: Add a `POST /api/reload` endpoint that calls
  `reload_config()` on all active coordinators. No request body needed — it just
  re-reads from disk.

- Frontend (`app.js` + `index.html`): Add a small reload button somewhere
  accessible (topbar or similar). On click, `POST /api/reload`, then show a toast
  confirming the reload. The frontend should also listen for the `config_changed`
  event on the WebSocket and refetch hotkeys/UI config when it arrives, so the
  current page reflects the new config without a full page reload.

### 3. Backends guide and documentation updates

**Problem:** The existing `docs/configuration/backends.md` explains the schema
and has worked examples, but it's terse. A new user doesn't know what backends
exist, how to install them, or how to verify they work. The README's install
section mentions Claude in passing but doesn't walk through a full setup.

**What to add:**

Expand `docs/configuration/backends.md` with a "Common backends" section
containing 2-3 full walkthroughs. Each should cover:

1. What the backend is (one sentence)
2. Prerequisites (Node.js, API key, etc.)
3. Install command
4. Config to add to `config.toml`
5. How to verify it works (start casebook, pick the backend, send a message)

**Candidates:**

- **Claude via claude-code-acp** — the primary backend. Install via npm, no
  config needed beyond the install (auto-detected on PATH). Mention that it uses
  ambient Anthropic credentials.
- **Gemini** — if there's an ACP-compatible adapter. The existing examples use
  `gemini --experimental-acp` which suggests there is one. Document the install,
  the API key env var, and the config.
- **Custom/generic** — a short section on "any ACP agent" for users building
  their own or using something not listed.

Also update the README:
- The Install section should link to the backends guide for full setup
  instructions rather than inlining a one-liner.
- Consider whether the Configuration section's example should show per-backend
  `default_model` instead of the top-level one.

## What NOT to do

- No in-app settings page or config editor.
- No bundled backend registry data file.
- No config-writing code (`save_global_config`, `tomli_w` dependency, etc.).
- No backend install/test/CRUD API endpoints.
- No `BackendRegistryEntry` or `load_registry()`.

## Files summary

| File | Changes |
|------|---------|
| `src/casebook/config.py` | Per-backend `default_model`, remove top-level `default_model` |
| `src/casebook/coordinator.py` | `reload_config()`, update `_apply_models()` |
| `src/casebook/web/server.py` | `POST /api/reload` endpoint |
| `src/casebook/web/static/app.js` | Reload button handler, `config_changed` event handling |
| `src/casebook/web/static/index.html` | Reload button element |
| `docs/configuration/backends.md` | Per-backend `default_model` schema, common backends walkthroughs |
| `docs/configuration/README.md` | Remove top-level `default_model`, update example |
| `README.md` | Update install/config sections |
