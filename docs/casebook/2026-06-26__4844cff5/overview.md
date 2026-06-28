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

## Deferred

- **Single binary packaging** (PyInstaller, Tauri, Rust rewrite) — deferred as a
  separate concern. The current architecture works well for Option C; packaging
  can be revisited when distribution becomes a priority.
