# Overview

This case covers improving casebook's user experience for first-time and
day-to-day use. The initial discussion evaluated options across three areas and
produced handoff documents for each, intended to springboard into separate
implementation sessions.

## Areas

### 1. App launching (auto-start + browser open) — IMPLEMENTED
**Decision:** Option C — a single `casebook` command that auto-starts the server
if not running and opens the browser. `--fg` for explicit foreground mode, `--stop`
to kill the daemon. No subcommands — flags only. Port is auto-selected (base
9721, increments on conflict) and recorded in `server.json`. See
`handoff-app-launching-auto-start-and-browser-open.md`.

### 2. Backend installation and configuration
**Decision:** A known-backends registry (data file bundled with casebook) plus a
UI for installing, configuring, and managing backends. Includes auto-install with
user confirmation. See `handoff-backend-installation-and-configuration-ux.md`.

### 3. Settings page and first-time onboarding
**Decision:** An in-app settings page covering backends, defaults, hotkeys, and
UI preferences. First-time onboarding via contextual banners rather than a
wizard. See `handoff-settings-page-and-first-time-onboarding.md`.

### 4. Friendly installation
**Decision:** Use `uv tool install git+https://github.com/<owner>/casebook` as
the primary install method. The package already has a standard `pyproject.toml`
with a `[project.scripts]` entrypoint and hatchling build backend, so this works
out of the box — users get an isolated venv, the `casebook` CLI on PATH, and
upgrades via `uv tool upgrade casebook`.

**Prerequisites to verify:**
- The built wheel must include everything needed at runtime (frontend assets,
  data files like the backends registry). The current
  `hatch.build.targets.wheel.packages` only lists `src/casebook`; bundled
  frontend or data files may need explicit inclusion.
- A build step (e.g. `justfile` target) should produce frontend assets before
  `uv build` for development/release workflows.

**Future considerations:**
- PyPI publication (`uv tool install casebook` without git URL) — friendlier but
  deferred until the project is ready for broader distribution.
- `pipx install` as an alternative for users without uv — same mechanism, worth
  mentioning in docs.

## Deferred

- **Single binary packaging** (PyInstaller, Tauri, Rust rewrite) — deferred as a
  separate concern. The current architecture works well for Option C; packaging
  can be revisited when distribution becomes a priority.
