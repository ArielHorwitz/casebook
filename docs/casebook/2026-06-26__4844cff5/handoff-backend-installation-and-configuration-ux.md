# Handoff: Backend installation and configuration UX

## Goal

Make it easy for users to discover, install, configure, and manage backends
without manually editing TOML files or knowing npm commands. This includes both
a UI for configuration and a registry of known backends with optional
auto-install.

## Current state

### Backend detection
- `src/casebook/config.py` defines two built-in backends:
  - **echo**: Always available, runs `sys.executable -m casebook.echo_backend`.
    A trivial reflect-back agent for testing.
  - **claude**: Available if `shutil.which("claude-code-acp")` finds the binary
    on PATH. Requires `npm install -g @zed-industries/claude-code-acp`.
- Built-in backends are defined in `builtin_backends()` in `config.py`.

### Custom backends
Users add backends in `config.toml`:
```toml
[backends.gemini]
command = ["gemini", "--experimental-acp"]
env = { GEMINI_API_KEY = "..." }
```
Config merges global (`~/.config/casebook/config.toml`) and project-local
(`.casebook/config.toml`), with project-local overriding per-backend.

### Pain points
- No guidance on what backends exist or how to install them.
- No validation that a configured backend actually works.
- No UI — pure TOML editing.
- The `claude` backend silently disappears if the binary isn't on PATH; the user
  just sees `echo` as the only option with no explanation.

## Design

### Known backends registry

A data file (TOML or JSON) bundled with casebook listing backends the app knows
about. Each entry:

```toml
[claude]
display_name = "Claude (Anthropic)"
description = "Anthropic's Claude via claude-code-acp"
binary = "claude-code-acp"             # what to look for on PATH
command = ["claude-code-acp"]          # how to run it
install_command = "npm install -g @zed-industries/claude-code-acp"
install_hint = "Requires Node.js and npm"
homepage = "https://github.com/anthropics/claude-code"
```

This registry is:
- **Bundled with casebook** — updated with each release.
- **Data, not code** — easy to add/remove/update entries without touching logic.
- **Separate from user config** — user's `config.toml` overrides/extends, never
  conflicts.

### UI components (part of settings page)

The settings page (see separate handoff) should include a backends section with:

1. **Installed backends list** — show each configured backend with:
   - Name, source (built-in / user-configured / registry)
   - Status: detected on PATH or not
   - Edit button (command, env vars)
   - Remove button (for user-configured ones)

2. **Available backends catalog** — from the registry, show backends not yet
   installed:
   - Name, description
   - Install button → shows the command that will be run, requires confirmation,
     streams output
   - "Already installed" indicator if binary is on PATH

3. **Add custom backend form** — for backends not in the registry:
   - Name, command (argv), environment variables
   - Test button: spawn the process briefly to verify it starts

### Auto-install flow

When the user clicks "Install" on a registry backend:
1. Show a confirmation dialog with the exact command
   (e.g., `npm install -g @zed-industries/claude-code-acp`).
2. Run the command server-side, streaming stdout/stderr back to the UI.
3. On success, re-scan PATH and update the backend status.
4. On failure, show the error output clearly.

Security consideration: this runs arbitrary shell commands from a web UI on
localhost. The confirmation dialog must clearly show what will execute. This is
acceptable for a local-only tool, but the UI should never auto-run without user
action.

### API endpoints needed

- `GET /api/backends` — list all backends (built-in + configured + registry),
  with installed/detected status.
- `POST /api/backends/{name}/install` — run the registry install command,
  stream output via SSE or WebSocket.
- `POST /api/backends` — add a custom backend (name, command, env).
- `PUT /api/backends/{name}` — update a backend's config.
- `DELETE /api/backends/{name}` — remove a user-configured backend.
- `POST /api/backends/{name}/test` — try spawning the backend briefly to verify
  it works.

### Config persistence

Backend changes made via the UI should be written to the global config file
(`~/.config/casebook/config.toml`). This means `config.py` needs a `save_config`
or `update_config` function — currently it only reads.

## Implementation notes

- The registry file could live at `src/casebook/data/backend_registry.toml` or
  similar.
- `config.py` already has the backend schema and merge logic; extending it for
  the registry should be straightforward.
- The install command execution needs subprocess management with output
  streaming — similar to how `engine/session.py` manages agent subprocesses,
  but simpler (no ACP protocol, just stdout/stderr).
- Backend detection (`shutil.which`) should be callable on-demand, not just at
  startup, so the UI can refresh after installation.

## Open questions

- Should the registry be fetched from a remote URL as well, allowing updates
  between releases? Adds complexity but future-proofs against rapid backend
  ecosystem changes.
- Should per-project backend overrides be editable from the UI, or only global
  config? Starting with global-only is simpler.
- How to handle backends that need API keys? The UI should support env var
  configuration, but should it store secrets in plaintext TOML? For now,
  probably yes (it's a local-only tool), but worth flagging.

## Files to modify

- `src/casebook/config.py` — add registry loading, config writing, on-demand
  backend detection
- `src/casebook/web/server.py` — add backend management API endpoints
- `src/casebook/web/static/app.js` — backend management UI (part of settings
  page)
- New: `src/casebook/data/backend_registry.toml` — known backends catalog

## Dependencies on other work

- **Settings page** — the backend management UI lives within the settings page.
  These can be developed together or the API can come first with UI following.
