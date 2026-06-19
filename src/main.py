#! /bin/python

import argparse
import datetime
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import tomllib

CASEBOOK_DIR = "docs/casebook"
AGENTS_MD_CANDIDATES = [
    "AGENTS.md",
    "agents.md",
    "Agents.md",
    ".agents/AGENTS.md",
    ".agents/agents.md",
    ".agents/Agents.md",
]

ROOT_AGENTS_EXCERPT = """\

## Casebook

This project uses a **casebook** at `docs/casebook/` to organize bounded units
of work — investigations, brainstorms, features, designs, and similar efforts
that benefit from a dedicated directory of files and documentation.

Historical cases and their context can be found there. See
`docs/casebook/agents.md` for structure and conventions.
"""

AGENTS_MD = """\
# Casebook

This directory is a **casebook** — a collection of cases, each representing a
bounded unit of work (investigation, brainstorm, feature, design, etc.).

## Structure

```
docs/casebook/
  agents.md          # this file
  YYYY-MM-DD__hex/   # case directory
    case.toml        # case metadata
    intro.md         # the user's original writeup (do not modify)
    overview.md      # evolving summary of the case (keep updated)
    ...              # any other files: reports, designs, ADRs, transcripts, etc.
```

## Working with cases

- New cases are created by the user via `casebook new` — agents should
  work within existing cases rather than creating new ones.
- `case.toml` is the `casebook` CLI's interface to the case — a fixed schema the
  tool parses for listing and discovery (`title`, `status`, `keywords`,
  `created`). It is owned by the tool: keep its fields current as the work
  evolves, but don't use it to record the case's content.
- `title` is the primary way cases are discovered, so it should capture the full
  scope of the case — anyone looking for this case's information should be able
  to find it by title. New cases default to "Unnamed case"; rename early and
  refine as the scope becomes clearer.
- `status` is typically `open` or `closed`, though others such as `blocked` or
  `paused` are fine too. Keep `keywords` updated to help future sessions find
  relevant cases.
- Beyond `case.toml`, list the case directory to see what files are available
  and read whichever are relevant to your task. These files hold the case's
  actual content — analysis, reports, decisions, designs, transcripts, etc.
  Code typically belongs in the source tree, not in the case directory.
- Use highly descriptive filenames so that an agent can understand what a file
  contains by reading its name alone. Prefer names like
  `websocket-reconnection-backoff-strategy.md` or
  `user-dashboard-layout-accessibility-review.md` over vague names like
  `report.md` or `notes.md`.
- Cases typically include an `intro.md` with the user's original writeup. This
  should not be modified — it is the original context, kept for posterity.
- Cases typically include an `overview.md` as a living summary of the case.
  Update this as the case evolves to keep it useful for future sessions.
- The casebook includes past cases that may provide historical context for
  design decisions, prior investigations, or previously considered approaches.
  Use `casebook list` to browse cases and `casebook show <id>` for details.
""".lstrip()

PREAMBLE_TEMPLATE = """\
Read the casebook directive at {casebook_dir}/agents.md and follow its conventions.
You are working on case `{case_id}`.
"""

CASE_TOML_TEMPLATE = """\
title = {title}
status = "open"
created = {created}
keywords = []
"""


def find_project_root() -> Path:
    current = Path.cwd()
    while True:
        if current.joinpath(CASEBOOK_DIR).is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    print(f"error: no casebook found (looking for {CASEBOOK_DIR}/)", file=sys.stderr)
    raise SystemExit(1)


def find_casebook_root() -> Path:
    return find_project_root() / CASEBOOK_DIR


def format_toml_value(value):
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        formatted = ", ".join(format_toml_value(item) for item in value)
        return f"[{formatted}]"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def cmd_init(args):
    casebook_path = Path.cwd() / CASEBOOK_DIR
    if casebook_path.exists() and not args.force:
        print(f"error: casebook already exists at {casebook_path}", file=sys.stderr)
        print("  Use --force to overwrite agents.md with the latest version")
        raise SystemExit(1)
    casebook_path.mkdir(parents=True, exist_ok=True)
    casebook_path.joinpath("agents.md").write_text(AGENTS_MD)
    if args.force:
        print(f"Updated agents.md at {casebook_path}")
    else:
        print(f"Initialized casebook at {casebook_path}")
        print("  Run 'casebook refer --insert' to add a pointer to your AGENTS.md")


def new_case_id() -> str:
    date_prefix = datetime.date.today().strftime("%Y-%m-%d")
    hex_suffix = secrets.token_hex(4)
    return f"{date_prefix}__{hex_suffix}"


def cmd_new(args):
    casebook_path = find_casebook_root()
    case_id = new_case_id()
    case_path = casebook_path / case_id
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR", "vi")
    intro_tmpfile = case_path.parent / f".casebook-intro-{case_id}.md"
    intro_tmpfile.write_text("")
    try:
        result = subprocess.run([editor, str(intro_tmpfile)])
        if result.returncode != 0:
            print("error: editor exited with non-zero status", file=sys.stderr)
            raise SystemExit(1)
        intro_content = intro_tmpfile.read_text()
    finally:
        intro_tmpfile.unlink(missing_ok=True)
    title = args.title or "Unnamed case"
    case_path.mkdir(parents=True)
    case_toml = CASE_TOML_TEMPLATE.format(
        title=format_toml_value(title),
        created=format_toml_value(datetime.datetime.now().isoformat()),
    )
    case_path.joinpath("case.toml").write_text(case_toml)
    if intro_content.strip():
        case_path.joinpath("intro.md").write_text(intro_content)
    preamble = PREAMBLE_TEMPLATE.format(
        casebook_dir=casebook_path,
        case_id=case_id,
    )
    case_path.joinpath(".preamble").write_text(preamble)
    print(f"Created case {case_id}: {title}")
    print(f"  {case_path}")


def is_case_hidden(case_path: Path) -> bool:
    return case_path.joinpath(".gitignore").exists()


def resolve_case(casebook_path: Path, case_id: str) -> Path:
    matches = [
        path
        for path in casebook_path.iterdir()
        if path.is_dir()
        and (path.name == case_id or path.name.split("__", 1)[-1].startswith(case_id))
    ]
    if not matches:
        print(f"error: no case matching '{case_id}'", file=sys.stderr)
        raise SystemExit(1)
    if len(matches) > 1:
        print(f"error: ambiguous case id '{case_id}', matches:", file=sys.stderr)
        for match in matches:
            print(f"  {match.name}", file=sys.stderr)
        raise SystemExit(1)
    return matches[0]


def load_case_metadata(case_path: Path) -> dict:
    toml_path = case_path / "case.toml"
    if not toml_path.exists():
        return {}
    return tomllib.loads(toml_path.read_text())


def cmd_list(args):
    casebook_path = find_casebook_root()
    cases = sorted(
        path
        for path in casebook_path.iterdir()
        if path.is_dir() and path.joinpath("case.toml").exists()
    )
    if not cases:
        print("No cases found.")
        return
    status_filter = args.status
    keyword_filter = args.keyword
    matched = []
    for case_path in cases:
        metadata = load_case_metadata(case_path)
        if status_filter and metadata.get("status") != status_filter:
            continue
        if keyword_filter:
            case_keywords = metadata.get("keywords", [])
            if keyword_filter not in case_keywords:
                continue
        matched.append((case_path, metadata))
    if not matched:
        print("No cases match the filter.")
        return
    for case_path, metadata in matched:
        case_id = case_path.name
        title = metadata.get("title", "(untitled)")
        status = metadata.get("status", "unknown")
        hidden = "  [hidden]" if is_case_hidden(case_path) else ""
        print(f"  {case_id}  [{status}]{hidden}  {title}")


def cmd_show(args):
    casebook_path = find_casebook_root()
    case_path = resolve_case(casebook_path, args.case_id)
    metadata = load_case_metadata(case_path)
    hidden = " [hidden]" if is_case_hidden(case_path) else ""
    print(f"Case: {case_path.name}{hidden}")
    print(f"Path: {case_path}")
    for key, value in metadata.items():
        print(f"  {key}: {value}")
    files = sorted(
        path.name for path in case_path.iterdir() if path.name != "case.toml"
    )
    if files:
        print("--- files ---")
        for filename in files:
            print(f"  {filename}")


def has_tracked_files(case_path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(case_path)],
        capture_output=True,
    )
    return result.returncode == 0


def cmd_delete(args):
    casebook_path = find_casebook_root()
    case_path = resolve_case(casebook_path, args.case_id)
    metadata = load_case_metadata(case_path)
    title = metadata.get("title", "(untitled)")
    if not args.force:
        print(f"Delete case {case_path.name}: {title}")
        response = input("Are you sure? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            return
    shutil.rmtree(case_path)
    print(f"Deleted case: {case_path.name}")


def find_agents_md() -> Path:
    project_root = find_project_root()
    for candidate in AGENTS_MD_CANDIDATES:
        path = project_root / candidate
        if path.exists():
            return path
    print("error: no AGENTS.md found in project root", file=sys.stderr)
    raise SystemExit(1)


def cmd_refer(args):
    if args.insert:
        agents_md = find_agents_md()
        with agents_md.open("a") as file:
            file.write(ROOT_AGENTS_EXCERPT)
        print(f"Appended casebook reference to {agents_md}")
    else:
        print(ROOT_AGENTS_EXCERPT)


def cmd_preamble(args):
    casebook_path = find_casebook_root()
    case_path = resolve_case(casebook_path, args.case_id)
    preamble = PREAMBLE_TEMPLATE.format(
        casebook_dir=casebook_path,
        case_id=case_path.name,
    )
    if args.save:
        preamble_path = case_path / ".preamble"
        preamble_path.write_text(preamble)
        print(f"Saved preamble to {preamble_path}")
    else:
        print(preamble, end="")


def cmd_hide(args):
    casebook_path = find_casebook_root()
    case_path = resolve_case(casebook_path, args.case_id)
    gitignore_path = case_path / ".gitignore"
    if is_case_hidden(case_path):
        gitignore_path.unlink()
        print(f"Unhidden case: {case_path.name}")
    else:
        gitignore_path.write_text("*\n")
        print(f"Hidden case: {case_path.name}")
        if has_tracked_files(case_path):
            print(
                f"  \033[1;33mWARNING: this case has files tracked by git. "
                f"Run: git rm -r --cached {case_path}\033[0m",
                file=sys.stderr,
            )


def main():
    parser = argparse.ArgumentParser(
        prog="casebook",
        description="Manage a project casebook for organizing investigations, "
        "brainstorms, features, and other bounded units of work.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init", help="Initialize a casebook in the current project"
    )
    init_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite agents.md if casebook exists",
    )

    new_parser = subparsers.add_parser("new", help="Create a new case")
    new_parser.add_argument(
        "-t", "--title", help="Case title (default: 'Unnamed case')"
    )

    list_parser = subparsers.add_parser("list", help="List cases")
    list_parser.add_argument("-s", "--status", help="Filter by status")
    list_parser.add_argument("-k", "--keyword", help="Filter by keyword")

    show_parser = subparsers.add_parser("show", help="Show case details")
    show_parser.add_argument(
        "case_id", help="Full case directory name or hex ID prefix"
    )

    hide_parser = subparsers.add_parser(
        "hide", help="Toggle case visibility in version control"
    )
    hide_parser.add_argument(
        "case_id", help="Full case directory name or hex ID prefix"
    )

    delete_parser = subparsers.add_parser("delete", help="Delete a case")
    delete_parser.add_argument(
        "case_id", help="Full case directory name or hex ID prefix"
    )
    delete_parser.add_argument(
        "-f", "--force", action="store_true", help="Skip confirmation"
    )

    preamble_parser = subparsers.add_parser(
        "preamble", help="Print or save the session preamble for a case"
    )
    preamble_parser.add_argument(
        "case_id", help="Full case directory name or hex ID prefix"
    )
    preamble_parser.add_argument(
        "-s",
        "--save",
        action="store_true",
        help="Save to .preamble in the case directory",
    )

    refer_parser = subparsers.add_parser(
        "refer", help="Print or insert a casebook reference into AGENTS.md"
    )
    refer_parser.add_argument(
        "-i",
        "--insert",
        action="store_true",
        help="Append the reference to the project's AGENTS.md",
    )

    args = parser.parse_args()

    if shutil.which("casebook") is None:
        print(
            "\033[1;33mWARNING: 'casebook' is not installed in PATH\033[0m",
            file=sys.stderr,
        )

    if args.command == "init":
        cmd_init(args)
    elif args.command == "new":
        cmd_new(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "refer":
        cmd_refer(args)
    elif args.command == "preamble":
        cmd_preamble(args)
    elif args.command == "hide":
        cmd_hide(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
