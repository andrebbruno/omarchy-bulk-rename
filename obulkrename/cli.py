"""omarchy-bulk-rename — rename a pile of files at once, with a preview first.

    omarchy-bulk-rename                          the menu, on the files you copied
    omarchy-bulk-rename replace " " _ *.jpg      one rule, straight away
    omarchy-bulk-rename undo                     put the last batch back
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from . import __version__, menu, plan as planning, rules
from .plan import Plan
from .rules import RuleError

STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                         "omarchy-bulk-rename")
JOURNAL = os.path.join(STATE_DIR, "last.json")

ICONS = {"file": "", "rule": "", "undo": "", "ok": "",
         "warn": "", "target": ""}


# ---------------------------------------------------------------- which files

def files_from_clipboard() -> list[str]:
    """What a file manager puts on the clipboard when you copy files."""
    from urllib.parse import unquote, urlparse
    try:
        r = subprocess.run(["wl-paste", "--type", "text/uri-list"],
                           capture_output=True, check=False)
    except OSError:
        return []
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            u = urlparse(line)
            if u.scheme == "file" and u.netloc in ("", "localhost"):
                path = unquote(u.path)
                if os.path.lexists(path):
                    out.append(path)
    return out


def files_from_cwd() -> list[str]:
    return sorted(os.path.join(os.getcwd(), n) for n in os.listdir(os.getcwd())
                  if not n.startswith("."))


def resolve_files(args) -> list[str]:
    """Explicit paths win; then the clipboard; then the directory you are standing in."""
    if args.files:
        missing = [f for f in args.files if not os.path.lexists(f)]
        if missing:
            print(f"omarchy-bulk-rename: not found: {', '.join(missing)}", file=sys.stderr)
        return [os.path.abspath(f) for f in args.files if os.path.lexists(f)]
    from_clip = files_from_clipboard()
    if from_clip:
        return from_clip
    return files_from_cwd()


# ---------------------------------------------------------------- showing and doing

def show(plan: Plan, limit: int = 40) -> None:
    changes = plan.changes
    if not changes:
        print("Nothing would change.")
    else:
        width = max(len(os.path.basename(r.src)) for r in changes[:limit])
        for r in changes[:limit]:
            print(f"  {os.path.basename(r.src):<{width}}  →  {os.path.basename(r.dst)}")
        if len(changes) > limit:
            print(f"  … and {len(changes) - limit} more")
    for problem in plan.problems:
        print(f"  ! {problem}", file=sys.stderr)


def carry_out(plan: Plan, args) -> int:
    if not plan.ok:
        show(plan)
        print(f"omarchy-bulk-rename: refusing to rename anything "
              f"({len(plan.problems)} problem(s))", file=sys.stderr)
        return 1
    if not plan.changes:
        print("Nothing to rename.")
        return 0
    if args.dry_run:
        show(plan)
        print(f"({len(plan.changes)} file(s) would be renamed)")
        return 0
    if not args.yes and sys.stdin.isatty():
        show(plan)
        try:
            if input(f"Rename {len(plan.changes)} file(s)? [y/N] ").strip().lower() not in ("y", "yes"):
                return 1
        except (EOFError, KeyboardInterrupt):
            return 1
    try:
        done = planning.execute(plan, JOURNAL)
    except (OSError, RuleError) as e:
        print(f"omarchy-bulk-rename: {e}", file=sys.stderr)
        menu.notify("Bulk rename", str(e))
        return 1
    print(f"Renamed {len(done)} file(s). `omarchy-bulk-rename undo` puts them back.")
    menu.notify("Bulk rename", f"{len(done)} file(s) renamed")
    return 0


# ---------------------------------------------------------------- commands

def rule_from_args(args):
    name = args.command
    if name == "replace":
        if args.a is None:
            raise RuleError("usage: omarchy-bulk-rename replace <search> [replacement] [files…]")
        return rules.Replace(args.a, args.b or "", regex=args.regex,
                             case_sensitive=not args.ignore_case, first_only=args.first)
    if name == "prefix":
        return rules.Affix(prefix=args.a or "")
    if name == "suffix":
        return rules.Affix(suffix=args.a or "")
    if name == "number":
        return rules.Number(start=int(args.a) if args.a else 1,
                            pad=args.pad, template=args.template or "{name}-{n}")
    if name == "case":
        return rules.Case(kind=args.a or "lower")
    if name == "slug":
        return rules.Slug()
    if name == "unaccent":
        return rules.Unaccent()
    if name == "trim":
        return rules.Trim()
    if name == "date":
        return rules.DateStamp(fmt=args.a or "%Y-%m-%d",
                               template=args.template or "{date} {name}")
    if name == "extension":
        return rules.Extension(new=args.a or "")
    raise RuleError(f"unknown rule {name!r}")


def cmd_rule(args) -> int:
    paths = resolve_files(args)
    if not paths:
        print("omarchy-bulk-rename: no files", file=sys.stderr)
        return 1
    target = "extension" if args.command == "extension" else args.target
    try:
        plan = planning.build(paths, rule_from_args(args), target)
    except RuleError as e:
        print(f"omarchy-bulk-rename: {e}", file=sys.stderr)
        return 2
    return carry_out(plan, args)


def cmd_undo(args) -> int:
    renames = planning.read_journal(JOURNAL)
    if not renames:
        print("Nothing to undo.")
        return 1
    plan = planning.undo(renames)
    if not plan.ok:
        show(plan)
        print("omarchy-bulk-rename: cannot undo cleanly", file=sys.stderr)
        return 1
    if args.dry_run:
        show(plan)
        return 0
    try:
        done = planning.execute(plan)
    except (OSError, RuleError) as e:
        print(f"omarchy-bulk-rename: {e}", file=sys.stderr)
        return 1
    if os.path.exists(JOURNAL):
        os.replace(JOURNAL, JOURNAL + ".undone")   # so undo cannot be run twice
    print(f"Put {len(done)} file(s) back.")
    menu.notify("Bulk rename", f"{len(done)} file(s) restored")
    return 0


def cmd_list(args) -> int:
    for path in resolve_files(args):
        print(path)
    return 0


NAUTILUS_SCRIPT = os.path.expanduser("~/.local/share/nautilus/scripts/Bulk rename")
SHIPPED_SCRIPT = "/usr/share/omarchy-bulk-rename/nautilus/Bulk rename"


def cmd_setup(args) -> int:
    """Put the right-click entry in Nautilus and show the keybinding."""
    source = SHIPPED_SCRIPT
    if not os.path.exists(source):
        local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "nautilus", "Bulk rename")
        source = local if os.path.exists(local) else ""
    if not source:
        print("omarchy-bulk-rename: the Nautilus script was not found", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(NAUTILUS_SCRIPT), exist_ok=True)
    with open(source, "rb") as src, open(NAUTILUS_SCRIPT, "wb") as dst:
        dst.write(src.read())
    os.chmod(NAUTILUS_SCRIPT, 0o755)
    print(f"Installed {NAUTILUS_SCRIPT}")
    print("In Nautilus: select files → right click → Scripts → Bulk rename")
    print('\nFor a keybinding, in ~/.config/hypr/bindings.lua:\n'
          '  o.bind("SUPER + ALT + R", "Bulk rename", "omarchy-bulk-rename")')
    return 0


# ---------------------------------------------------------------- the menu

# How many arguments each rule takes before the file list starts. Without this,
# `omarchy-bulk-rename case upper photo.jpg` reads photo.jpg as the rule's second
# argument and then renames the whole directory instead.
ARITY = {"replace": 2, "prefix": 1, "suffix": 1, "number": 1, "case": 1, "date": 1,
         "extension": 1, "slug": 0, "unaccent": 0, "trim": 0}

MENU_RULES = [
    ("Search and replace", "Replace text in every name", "replace"),
    ("Replace with a pattern", "A regular expression, with \\1 in the replacement", "regex"),
    ("Add a prefix", "Before every name", "prefix"),
    ("Add a suffix", "After every name, before the extension", "suffix"),
    ("Number them", "photo-01, photo-02, …", "number"),
    ("Change the case", "lower, UPPER, Title or Sentence", "case"),
    ("Remove accents", "ação → acao", "unaccent"),
    ("Make a safe name", "lowercase-with-hyphens, no accents", "slug"),
    ("Tidy up spaces", "Collapse runs of spaces, trim the ends", "trim"),
    ("Add the date", "The file's own date, in front of the name", "date"),
    ("Change the extension", "For all of them at once", "extension"),
]


def cmd_menu(args) -> int:
    paths = resolve_files(args)
    if not paths:
        menu.notify("Bulk rename", "No files — copy some in the file manager first")
        return 1

    where = os.path.basename(os.path.dirname(paths[0])) or "/"
    rows = [(ICONS["rule"], label, hint) for label, hint, _ in MENU_RULES]
    if planning.read_journal(JOURNAL):
        rows.append((ICONS["undo"], "Undo the last rename", "Put the previous batch back"))
    pick = menu.select(f"Rename {len(paths)} file(s) in {where}", rows, width=640)
    if not pick:
        return 1
    label = pick.split("\t")[0]
    if label == "Undo the last rename":
        args.dry_run = False
        return cmd_undo(args)

    kind = next((k for lbl, _, k in MENU_RULES if lbl == label), None)
    rule, target = build_rule_from_menu(kind)
    if rule is None:
        return 1
    plan = planning.build(paths, rule, target)
    return confirm_in_menu(plan, args)


def build_rule_from_menu(kind: str | None):
    """Ask for whatever the chosen rule needs, one prompt at a time."""
    target = "name"
    try:
        if kind in ("replace", "regex"):
            search = menu.ask("Find what?" if kind == "replace" else "Find what? (regex)")
            if not search:
                return None, target
            replace = menu.ask(f"Replace {search!r} with what? (leave empty to delete)") or ""
            return rules.Replace(search, replace, regex=(kind == "regex")), target
        if kind == "prefix":
            value = menu.ask("Prefix")
            return (rules.Affix(prefix=value), target) if value else (None, target)
        if kind == "suffix":
            value = menu.ask("Suffix")
            return (rules.Affix(suffix=value), target) if value else (None, target)
        if kind == "number":
            template = menu.ask("Pattern ({name} and {n})", ) or "{name}-{n}"
            return rules.Number(template=template), target
        if kind == "case":
            pick = menu.select("Which case?",
                               [(ICONS["rule"], k, f"example → {rules.Case(k).transform('meu Arquivo', 0, '')}")
                                for k in rules.Case.KINDS], width=520)
            return (rules.Case(pick.split("\t")[0]), target) if pick else (None, target)
        if kind == "unaccent":
            return rules.Unaccent(), target
        if kind == "slug":
            return rules.Slug(), target
        if kind == "trim":
            return rules.Trim(), target
        if kind == "date":
            fmt = menu.ask("Date format (strftime)") or "%Y-%m-%d"
            return rules.DateStamp(fmt=fmt), target
        if kind == "extension":
            value = menu.ask("New extension (without the dot)")
            return (rules.Extension(value), "extension") if value else (None, target)
    except RuleError as e:
        menu.notify("Bulk rename", str(e))
        return None, target
    return None, target


def confirm_in_menu(plan: Plan, args) -> int:
    """The preview, as a menu: every line is what will happen, and the first row decides."""
    if not plan.ok:
        menu.notify("Bulk rename", plan.problems[0])
        return 1
    if not plan.changes:
        menu.notify("Bulk rename", "Nothing would change")
        return 0
    rows = [(ICONS["ok"], f"Rename {len(plan.changes)} file(s)", "Go ahead")]
    rows += [(ICONS["file"], os.path.basename(r.src), f"→ {os.path.basename(r.dst)}")
             for r in plan.changes[:60]]
    pick = menu.select("Preview", rows, width=700)
    if not pick or not pick.startswith("Rename "):
        return 1
    args.yes = True
    args.dry_run = False
    return carry_out(plan, args)


# ---------------------------------------------------------------- entry point

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="omarchy-bulk-rename",
        description="Rename a pile of files at once, with a preview first.",
        epilog="With no rule, the Omarchy menu opens on the files you copied "
               "in the file manager (or on the current directory).")
    p.add_argument("command", nargs="?",
                   help="replace, regex, prefix, suffix, number, case, slug, unaccent, "
                        "trim, date, extension, undo, list, setup")
    p.add_argument("a", nargs="?", help="the rule's first argument")
    p.add_argument("b", nargs="?", help="the rule's second argument")
    p.add_argument("files", nargs="*", help="which files (default: the clipboard, then .)")
    p.add_argument("-n", "--dry-run", action="store_true", help="show the plan, change nothing")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask")
    p.add_argument("-e", "--regex", action="store_true", help="for replace: a regular expression")
    p.add_argument("-i", "--ignore-case", action="store_true", help="for replace: ignore case")
    p.add_argument("--first", action="store_true", help="for replace: only the first match")
    p.add_argument("--pad", type=int, default=2, help="for number: digits (default 2)")
    p.add_argument("--template", help="for number and date: the pattern")
    p.add_argument("--target", choices=("name", "extension", "full"), default="name",
                   help="which part of the filename the rule sees (default: name)")
    p.add_argument("-V", "--version", action="version", version=f"omarchy-bulk-rename {__version__}")
    args = p.parse_args(argv)

    if args.command is None:
        return cmd_menu(args)
    if args.command == "undo":
        return cmd_undo(args)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "regex":
        args.command, args.regex = "replace", True
    if args.command not in ARITY:
        # Not a rule: treat it as a file, so `omarchy-bulk-rename *.jpg` opens the menu.
        args.files = [args.command, *(x for x in (args.a, args.b) if x), *args.files]
        args.command = None
        return cmd_menu(args)

    # Give back the positionals this rule does not want; they are files.
    takes = ARITY[args.command]
    if takes < 2 and args.b:
        args.files.insert(0, args.b)
        args.b = None
    if takes < 1 and args.a:
        args.files.insert(0, args.a)
        args.a = None
    return cmd_rule(args)


if __name__ == "__main__":
    sys.exit(main())
