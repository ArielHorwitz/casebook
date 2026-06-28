# Handoff: Settings page and first-time onboarding

## Goal

Add a settings page to the app that serves as both the configuration UI and the
entry point for first-time users. Replace the current "edit TOML files manually"
workflow with an in-app experience.

## Current state

### Configuration
- All config is in TOML files: global (`~/.config/casebook/config.toml`) and
  project-local (`.casebook/config.toml`).
- Config is read once at startup by `CaseCoordinator.__init__` (via
  `load_config()` in `config.py`). Changes require a server restart.
- No UI for viewing or modifying configuration.

### What's configurable today
From `config.py`, the full schema:

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `default_backend` | string | `"claude"` or `"echo"` | Default for new sessions |
| `default_model` | string | — | Model preference |
| `default_always_allow` | bool | `false` | Auto-allow permissions |
| `naming_prompt` | string | built-in | Session naming instructions |
| `naming_backend` | string | session's backend | Backend for naming |
| `naming_model` | string | — | Model for naming |
| `[backends.*]` | table | echo + claude | Backend definitions |
| `[hotkeys]` | table | built-in defaults | Keyboard shortcut rebindings |
| `[ui]` | table | `50%`/`320px`/`none` | Session column sizing |

### First-time experience
Currently: the user sees the project browser. If no backends are configured
(or claude-code-acp isn't installed), they can only use the echo backend, with
no explanation of why or how to set up a real backend.

## Design

### Settings page structure

A new route at `/settings` (or a modal/panel accessible from any page via a gear
icon or hotkey). Sections:

#### 1. Backends
See the backend installation handoff for full details. Summary:
- List of configured backends with status
- Install known backends from registry
- Add/edit/remove custom backends

#### 2. Defaults
- Default backend (dropdown of configured backends)
- Default model (text input — validated against available models at session
  creation time, not here)
- Default always-allow (toggle)

#### 3. Session naming
- Naming backend (dropdown)
- Naming model (text input)
- Naming prompt (textarea, with "reset to default" button)

#### 4. Hotkeys
- Table of all bindable actions with current bindings
- Click-to-rebind interface (press the new key combo)
- Reset individual bindings or all to defaults
- The hotkey help modal (`?`) already lists actions — this section makes them
  editable

#### 5. UI
- Session column width, min-width, max-width (sliders or text inputs with live
  preview)

#### 6. About
- Casebook version
- Link to documentation/repo
- Backend versions (if detectable)

### First-time onboarding

Rather than a separate wizard, use contextual guidance:

1. **Empty project browser** — when no projects exist, show a welcome message
   with:
   - Brief explanation of what casebook does
   - "Open a project" button/instructions
   - Link to settings if no usable backend is detected

2. **No backend banner** — when the only available backend is echo, show a
   persistent but dismissible banner: "No AI backend configured.
   [Set up a backend →]" linking to the backends section of settings.

3. **Settings page guidance** — each section has a brief description of what it
   controls. The backends section is self-documenting via the registry (see
   backend handoff).

This avoids a wizard (which gets stale and users skip) while still making the
path forward obvious.

### Hot-reload vs. restart

Currently config is loaded once at startup. For the settings page to be useful,
changes need to take effect without restarting:

- **Backends**: Can be reloaded by re-running `load_config()` and updating the
  coordinator's backend list. New sessions use new config; existing sessions
  keep their backend.
- **Defaults**: Simple — just re-read on next session creation.
- **Hotkeys**: Already sent to the frontend via the initial page load. Would
  need a WebSocket message to push updated hotkeys, or the frontend refetches
  on settings save.
- **UI sizing**: CSS variables — can be updated live via WebSocket or on next
  page load.

Recommendation: on settings save, write the TOML file, re-run `load_config()`,
and broadcast a "config_changed" event over WebSocket so the frontend can
refetch what it needs.

### API endpoints needed

- `GET /api/config` — return current effective config (merged global + project).
- `PUT /api/config` — update global config (write to
  `~/.config/casebook/config.toml`). Accepts partial updates.
- `GET /api/config/defaults` — return default values for all settings (so the
  UI can show "reset to default" buttons).
- Backend-specific endpoints — see backend handoff.

### Frontend routing

The app uses hash-based client-side routing in `app.js`. Add:
- `/settings` route → renders the settings page
- Navigation link: gear icon in the header/sidebar, accessible from any page
- Hotkey: consider binding a key to open settings (e.g., `,` which is common
  in many apps)

## Implementation notes

- `app.js` is ~1250 lines of vanilla JS with client-side routing. The settings
  page would be another `render*` function following the existing pattern.
- Config writing is new — `config.py` currently only reads. Need a
  `save_global_config(updates)` function that reads the existing file, merges
  updates, and writes back. Must preserve comments and formatting as much as
  possible (consider `tomlkit` instead of `tomllib` for round-trip fidelity, or
  accept that saving from UI will normalize formatting).
- The hotkey system already has a complete action registry
  (`DEFAULT_HOTKEYS` in `config.py` and the `?` modal in the frontend). The
  settings page can reuse this list.

## Open questions

- Should project-local config be editable from the UI? This adds complexity
  (which config file am I editing?) but is useful for per-project backend
  overrides. Could defer to a later iteration.
- Should the settings page be a full route or a slide-out panel/modal? A full
  route is simpler to implement and easier to link to from onboarding banners.
- `tomlkit` for round-trip TOML editing vs. `tomllib` (read-only, stdlib) +
  `tomli_w` (write-only, loses comments). If users have comments in their
  config files, losing them on save would be frustrating.

## Files to modify

- `src/casebook/config.py` — add config writing, defaults export
- `src/casebook/web/server.py` — add config API endpoints, config-changed event
- `src/casebook/web/static/app.js` — settings page UI, onboarding banners
- `src/casebook/web/static/style.css` — settings page styling
- `src/casebook/coordinator.py` — handle config reload, broadcast config changes

## Dependencies

- **Backend installation** — the backends section of settings depends on the
  backend registry and install flow described in the backend handoff.
- **App launching** — independent; settings page works regardless of how the
  server is started.
