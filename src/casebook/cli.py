"""Command-line entry point.

Usage:
    casebook                       # start daemon + open browser
    casebook /path/to/project      # start daemon + open browser to project
    casebook --fg                  # foreground server + open browser
    casebook --fg --no-browser     # foreground server, no browser
    casebook --stop                # stop running daemon
    casebook --restart             # stop running daemon, then start a fresh one
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import state

# The host shown in the browser's address bar. `casebook.localhost` is nicer to
# read and recognise than a bare loopback IP; browsers resolve any `*.localhost`
# name to the loopback interface per RFC 6761, so it reaches the same IPv4-bound
# server with no DNS or hosts-file setup. Set CASEBOOK_BROWSER_HOST=127.0.0.1 to
# fall back to the raw IP (e.g. on a browser or resolver that doesn't honour
# `.localhost`). Only affects the opened URL — the server still binds --host.
DEFAULT_BROWSER_HOST = "casebook.localhost"


def _open_browser(port: int, project_path: str | None = None) -> None:
    """Open the browser to the casebook UI, optionally at a project page."""
    from urllib.parse import quote
    host = os.environ.get("CASEBOOK_BROWSER_HOST") or DEFAULT_BROWSER_HOST
    base_url = f"http://{host}:{port}"
    if project_path is not None:
        resolved = str(Path(project_path).resolve())
        url = f"{base_url}/?path={quote(resolved, safe='/')}"
    else:
        url = base_url
    webbrowser.open(url)


def _wait_for_server(timeout: float = 5.0, interval: float = 0.05) -> state.ServerInfo | None:
    """Poll for server.json to appear, then verify the server is responding."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = state.read_server_info()
        if info is not None and state.is_port_responding(info.port):
            return info
        time.sleep(interval)
    return None


def _start_daemon(host: str) -> state.ServerInfo:
    """Spawn a background casebook server and wait for it to be ready."""
    # The detached daemon has no terminal, so redirect its stdout/stderr into the
    # log. Structured events (via the logger's stream handler), uvicorn output,
    # and any pre-logging crash all land in this one file, in order. Append so a
    # crash log survives across restarts. CASEBOOK_LOG_PATH overrides the path.
    log = Path(os.environ.get("CASEBOOK_LOG_PATH") or state.log_path())
    log.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log, "a")  # noqa: SIM115 — kept open for the child's lifetime

    subprocess.Popen(
        [sys.executable, "-m", "casebook", "--fg", "--no-browser", "--host", host],
        start_new_session=True,
        stdout=log_file,
        stderr=log_file,
        env={**os.environ, "CASEBOOK_DAEMON": "1"},
    )

    info = _wait_for_server()
    if info is None:
        print(f"Server failed to start. Check logs at {log}", file=sys.stderr)
        sys.exit(1)
    return info


def cmd_stop() -> None:
    """Stop a running daemon."""
    if state.stop_server():
        print("Server stopped.")
    else:
        print("No running server found.", file=sys.stderr)
        sys.exit(1)


def cmd_foreground(host: str, open_browser: bool, project_path: str | None) -> None:
    """Run the server in the foreground.

    Whether this instance owns ``server.json`` is decided inside ``serve()`` by
    the ``CASEBOOK_DAEMON`` marker: the spawned daemon is the singleton, a
    user-run ``--fg`` is isolated and touches no shared state.
    """
    from .web.server import serve

    port = state.find_available_port(host=host)
    serve(host=host, port=port, open_browser=open_browser, project_path=project_path)


def cmd_default(host: str, project_path: str | None) -> None:
    """Auto-start daemon if needed, then open browser."""
    info = state.find_running_server()
    if info is None:
        info = _start_daemon(host)
        print(f"Server started on port {info.port} (pid {info.pid}).")
    _open_browser(info.port, project_path)


def cmd_restart(host: str, project_path: str | None) -> None:
    """Stop any running daemon, then start a fresh one and open the browser."""
    stopped = state.stop_server(wait=True)
    if stopped is not None:
        print(f"Stopped server on port {stopped.port} (pid {stopped.pid}).")
    cmd_default(host=host, project_path=project_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="casebook",
        description="Organize bounded units of work and coordinate agents over them.",
    )
    parser.add_argument("project", nargs="?", default=None,
                        help="Path to a project directory to open")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--fg", "--foreground", action="store_true", dest="foreground",
                        help="Run the server in the foreground")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't open the browser (only with --fg)")
    parser.add_argument("--stop", action="store_true",
                        help="Stop a running daemon")
    parser.add_argument("--restart", action="store_true",
                        help="Stop a running daemon, then start a fresh one")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.stop:
        cmd_stop()
    elif args.restart:
        cmd_restart(host=args.host, project_path=args.project)
    elif args.foreground:
        cmd_foreground(
            host=args.host,
            open_browser=not args.no_browser,
            project_path=args.project,
        )
    else:
        cmd_default(host=args.host, project_path=args.project)


if __name__ == "__main__":
    main()
