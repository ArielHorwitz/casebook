# Handoff: Auto-start server and open browser

## Goal

Replace the current `casebook serve` workflow with a single `casebook` command
that starts the server if needed and opens the browser to the right page. The
user should never have to think about whether the server is running.

## Decision

Auto-start server if not running, then open browser. The Jupyter model — one
command, it just works. Unix-only for now.

## Current state

- `casebook serve` (the only CLI command) runs Uvicorn in the foreground,
  blocking the terminal. No daemon mode, no PID file, no port probing.
- Entry point: `src/casebook/cli.py` → calls `serve()` in
  `src/casebook/web/server.py`.
- `serve()` calls `uvicorn.run(create_app(), host, port, log_level="warning")`.
- The terminal shows session activity while running ("all sessions idle", etc.).
- Registered in `pyproject.toml` as `casebook = "casebook.cli:main"`.

## CLI interface

No subcommands — flags only.

```
casebook                       → auto-start daemon + open browser
casebook /some/path            → auto-start daemon + open browser to project
casebook --fg                  → foreground server + open browser
casebook --fg --no-browser     → foreground server, no browser (scripting/systemd)
casebook --stop                → kill daemon
```

- `--fg` / `--foreground`: run server in foreground instead of daemonizing.
  Opens browser by default (suppress with `--no-browser`).
- `--stop`: kill a running daemon via PID from server info file, then exit.
- `--no-browser`: suppress browser open (only meaningful with `--fg`; in daemon
  mode the whole point is to open the browser).
- `--host`: bind address, default `127.0.0.1`. Applies to both modes.
- Positional argument: if present and not a flag, treated as a project path.
  The project is opened/registered and the browser navigates to its page.

## Port selection

No fixed default port. On daemon start (or foreground start without `--port`):

1. Start from a base port (e.g. 9721).
2. Try to bind; if the port is in use, increment and retry.
3. Write the actual bound port to the server info file.

Second invocations discover the port by reading the server info file — no need
for the client to know the port in advance.

No `--port` flag — the port is an internal detail.

## Server info file

Location: `$XDG_STATE_HOME/casebook/server.json` (falls back to
`~/.local/state/casebook/server.json`).

```json
{"pid": 12345, "port": 9721, "started": "2026-06-28T14:30:00"}
```

Written by the daemon on startup. Read by subsequent `casebook` invocations and
by `--stop`. Removed on clean shutdown.

## Daemon logs

Location: `$XDG_STATE_HOME/casebook/casebook.log` (same directory as server
info).

Overwritten on each daemon start — no log rotation. The daemon's stdout/stderr
are redirected here.

## Server detection (is a daemon already running?)

On `casebook` invocation:

1. Read `server.json`. If missing → no server running, start one.
2. Check if `pid` is alive (`os.kill(pid, 0)`).
3. Probe `localhost:{port}` to confirm it's responding.
4. If both pass → server is running; just open the browser.
5. If pid is dead or port isn't responding → stale file; remove it, start a new
   daemon.

## Daemonization

`subprocess.Popen` re-invoking `casebook --fg --no-browser` with
`start_new_session=True`, stdout/stderr redirected to the log file. This keeps
the daemon as a normal foreground server process, just backgrounded.

The daemon process writes `server.json` after binding the port (so the file
always has the correct port). The parent process polls for the file to appear,
then reads the port and opens the browser.

Startup sequence:

1. Parent spawns child via `Popen`.
2. Child binds port (auto-selecting if needed), writes `server.json`, starts
   serving.
3. Parent polls for `server.json` (short sleep intervals, ~50ms, ~5s timeout).
4. Parent reads port from `server.json`, opens browser, exits.

## Browser opening

`webbrowser.open(url)` — works on Linux and macOS.

In foreground mode (`--fg`), hook into uvicorn/starlette's startup event to open
the browser after the server is actually listening, rather than polling.

## Stopping

`casebook --stop`:

1. Read `server.json`.
2. `os.kill(pid, signal.SIGTERM)`.
3. Remove `server.json`.

No shutdown endpoint needed — signals work fine on Unix.

The server should also clean up `server.json` on graceful shutdown (SIGTERM
handler or atexit).

## Files to modify

- `src/casebook/cli.py` — rewrite: flag-based interface, daemon management,
  browser open logic.
- `src/casebook/web/server.py` — add server info file writing (port + pid after
  bind), cleanup on shutdown. May need to refactor `serve()` to support writing
  the info file after the port is bound but before entering the serve loop.
- New: `src/casebook/state.py` (or similar) — `state_dir()` helper returning the
  XDG state directory, server info file read/write/cleanup utilities.

## Not in scope

- systemd unit file generation
- Single-binary packaging
- Tray icon or native wrapper
- Windows support
