"""Command-line entry point.

The CLI is a thin shell that launches the casebook web app.
"""

from __future__ import annotations

import argparse


def cmd_serve(args) -> None:
    from .web.server import serve  # lazy: keeps import-light

    serve(host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="casebook",
        description="Organize bounded units of work and coordinate agents over them.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cmd_serve(args)


if __name__ == "__main__":
    main()
