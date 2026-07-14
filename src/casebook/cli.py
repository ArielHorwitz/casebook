"""Command-line entry point.

Usage:
    casebook                       # start daemon + open browser
    casebook /path/to/project      # start daemon + open browser to project
    casebook --fg                  # foreground server + open browser
    casebook --fg --no-browser     # foreground server, no browser
    casebook --stop                # stop running daemon
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


def _open_browser(port: int, project_path: str | None = None) -> None:
    """Open the browser to the casebook UI, optionally at a project page."""
    from urllib.parse import quote
    base_url = f"http://127.0.0.1:{port}"
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
    # Structured logging owns casebook.log; the raw stdout/stderr redirect goes to
    # a separate file so it can capture crashes and uvicorn output (and anything
    # before logging is configured) without fighting the rotating file handler.
    err = state.daemon_err_path()
    err.parent.mkdir(parents=True, exist_ok=True)
    err_file = open(err, "w")  # noqa: SIM115 — kept open for the child's lifetime

    subprocess.Popen(
        [sys.executable, "-m", "casebook", "--fg", "--no-browser", "--host", host],
        start_new_session=True,
        stdout=err_file,
        stderr=err_file,
        env={**os.environ, "CASEBOOK_DAEMON": "1"},
    )

    info = _wait_for_server()
    if info is None:
        print(f"Server failed to start. Check logs at {state.log_path()} "
              f"(errors: {err})", file=sys.stderr)
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
    """Run the server in the foreground."""
    from .web.server import serve

    port = state.find_available_port(host=host)
    if open_browser:
        # We schedule the browser open via uvicorn's startup event inside serve().
        pass
    serve(host=host, port=port, write_info=True, open_browser=open_browser,
          project_path=project_path)


def cmd_default(host: str, project_path: str | None) -> None:
    """Auto-start daemon if needed, then open browser."""
    info = state.find_running_server()
    if info is None:
        info = _start_daemon(host)
        print(f"Server started on port {info.port} (pid {info.pid}).")
    _open_browser(info.port, project_path)


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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.stop:
        cmd_stop()
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
