"""Command-line entry point.

Keeps the original casebook commands (init/new/list/show/hide/delete/preamble/
refer) and adds `serve`, which launches the coordinator app. The CLI is a thin
shell over cases.py and templates.py; the app is a thin shell over the engine.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import cases, templates

AGENTS_MD_CANDIDATES = [
    "AGENTS.md",
    "agents.md",
    "Agents.md",
    ".agents/AGENTS.md",
    ".agents/agents.md",
    ".agents/Agents.md",
]


def cmd_init(args) -> None:
    casebook_path = Path.cwd().joinpath(cases.CASEBOOK_DIR)
    if casebook_path.exists() and not args.force:
        print(f"error: casebook already exists at {casebook_path}", file=sys.stderr)
        print("  Use --force to overwrite agents.md with the latest version")
        raise SystemExit(1)
    casebook_path.mkdir(parents=True, exist_ok=True)
    casebook_path.joinpath("agents.md").write_text(templates.AGENTS_MD)
    if args.force:
        print(f"Updated agents.md at {casebook_path}")
    else:
        print(f"Initialized casebook at {casebook_path}")
        print("  Run 'casebook refer --insert' to add a pointer to your AGENTS.md")


def cmd_new(args) -> None:
    casebook_path = cases.find_casebook_root()
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR", "vi")
    tmpfile = casebook_path.joinpath(f".casebook-intro-{cases.new_case_id()}.md")
    tmpfile.write_text("")
    try:
        result = subprocess.run([editor, str(tmpfile)])
        if result.returncode != 0:
            print("error: editor exited with non-zero status", file=sys.stderr)
            raise SystemExit(1)
        intro = tmpfile.read_text()
    finally:
        tmpfile.unlink(missing_ok=True)
    case = cases.create_case(casebook_path, args.title or "Unnamed case", intro)
    print(f"Created case {case.case_id}: {case.title}")
    print(f"  {case.path}")


def cmd_list(args) -> None:
    casebook_path = cases.find_casebook_root()
    matched = cases.list_cases(casebook_path, status=args.status, keyword=args.keyword)
    if not matched:
        print("No cases match." if (args.status or args.keyword) else "No cases found.")
        return
    for case in matched:
        hidden = "  [hidden]" if case.hidden else ""
        print(f"  {case.case_id}  [{case.status}]{hidden}  {case.title}")


def cmd_show(args) -> None:
    casebook_path = cases.find_casebook_root()
    case = cases.resolve_case(casebook_path, args.case_id)
    hidden = " [hidden]" if case.hidden else ""
    print(f"Case: {case.case_id}{hidden}")
    print(f"Path: {case.path}")
    for key, value in case.metadata.items():
        print(f"  {key}: {value}")
    files = case.files()
    if files:
        print("--- files ---")
        for filename in files:
            print(f"  {filename}")


def cmd_delete(args) -> None:
    casebook_path = cases.find_casebook_root()
    case = cases.resolve_case(casebook_path, args.case_id)
    if not args.force:
        print(f"Delete case {case.case_id}: {case.title}")
        if input("Are you sure? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return
    shutil.rmtree(case.path)
    print(f"Deleted case: {case.case_id}")


def _has_tracked_files(case_path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(case_path)], capture_output=True
    )
    return result.returncode == 0


def cmd_hide(args) -> None:
    casebook_path = cases.find_casebook_root()
    case = cases.resolve_case(casebook_path, args.case_id)
    gitignore_path = case.path.joinpath(".gitignore")
    if case.hidden:
        gitignore_path.unlink()
        print(f"Unhidden case: {case.case_id}")
    else:
        gitignore_path.write_text("*\n")
        print(f"Hidden case: {case.case_id}")
        if _has_tracked_files(case.path):
            print(
                f"  \033[1;33mWARNING: this case has files tracked by git. "
                f"Run: git rm -r --cached {case.path}\033[0m",
                file=sys.stderr,
            )


def cmd_preamble(args) -> None:
    casebook_path = cases.find_casebook_root()
    case = cases.resolve_case(casebook_path, args.case_id)
    preamble = templates.PREAMBLE_TEMPLATE.format(
        casebook_dir=casebook_path, case_id=case.case_id
    )
    if args.save:
        path = case.path.joinpath(".preamble")
        path.write_text(preamble)
        print(f"Saved preamble to {path}")
    else:
        print(preamble, end="")


def _find_agents_md() -> Path:
    project_root = cases.find_project_root()
    for candidate in AGENTS_MD_CANDIDATES:
        path = project_root.joinpath(candidate)
        if path.exists():
            return path
    raise cases.CasebookError("no AGENTS.md found in project root")


def cmd_refer(args) -> None:
    if args.insert:
        agents_md = _find_agents_md()
        with agents_md.open("a") as file:
            file.write(templates.ROOT_AGENTS_EXCERPT)
        print(f"Appended casebook reference to {agents_md}")
    else:
        print(templates.ROOT_AGENTS_EXCERPT)


def cmd_serve(args) -> None:
    project_root = cases.find_project_root()
    from .web.server import serve  # lazy: keeps plain CLI commands import-light

    print(f"casebook serving {project_root}")
    print(f"  open http://{args.host}:{args.port}")
    serve(project_root, host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="casebook",
        description="Organize bounded units of work and coordinate agents over them.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a casebook")
    init_parser.add_argument("-f", "--force", action="store_true",
                             help="Overwrite agents.md if casebook exists")

    new_parser = subparsers.add_parser("new", help="Create a new case")
    new_parser.add_argument("-t", "--title", help="Case title (default: 'Unnamed case')")

    list_parser = subparsers.add_parser("list", help="List cases")
    list_parser.add_argument("-s", "--status", help="Filter by status")
    list_parser.add_argument("-k", "--keyword", help="Filter by keyword")

    show_parser = subparsers.add_parser("show", help="Show case details")
    show_parser.add_argument("case_id", help="Full case name or hex ID prefix")

    hide_parser = subparsers.add_parser("hide", help="Toggle case visibility in VCS")
    hide_parser.add_argument("case_id", help="Full case name or hex ID prefix")

    delete_parser = subparsers.add_parser("delete", help="Delete a case")
    delete_parser.add_argument("case_id", help="Full case name or hex ID prefix")
    delete_parser.add_argument("-f", "--force", action="store_true",
                               help="Skip confirmation")

    preamble_parser = subparsers.add_parser("preamble", help="Print/save a case preamble")
    preamble_parser.add_argument("case_id", help="Full case name or hex ID prefix")
    preamble_parser.add_argument("-s", "--save", action="store_true",
                                 help="Save to .preamble in the case directory")

    refer_parser = subparsers.add_parser("refer", help="Print/insert a casebook reference")
    refer_parser.add_argument("-i", "--insert", action="store_true",
                              help="Append the reference to the project's AGENTS.md")

    serve_parser = subparsers.add_parser("serve", help="Launch the casebook app")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)

    return parser


COMMANDS = {
    "init": cmd_init,
    "new": cmd_new,
    "list": cmd_list,
    "show": cmd_show,
    "delete": cmd_delete,
    "hide": cmd_hide,
    "preamble": cmd_preamble,
    "refer": cmd_refer,
    "serve": cmd_serve,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return
    try:
        handler(args)
    except cases.CasebookError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
