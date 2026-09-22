"""From a rule and a list of files to a rename plan — and from a plan to the disk.

The plan is built and checked in full before a single file moves. That is what makes the
preview honest: what it shows is the same list that will be carried out, refusing to start
if any of it would lose a file.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from .rules import RuleError

# What may not appear in a filename on any sane filesystem, plus the separator.
FORBIDDEN = set("/\0")
RESERVED = {".", ".."}


@dataclass
class Rename:
    src: str
    dst: str

    @property
    def changed(self) -> bool:
        return self.src != self.dst


@dataclass
class Plan:
    renames: list[Rename] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def changes(self) -> list[Rename]:
        return [r for r in self.renames if r.changed]

    def __len__(self) -> int:
        return len(self.changes)


def split_name(path: str, target: str) -> tuple[str, str, str]:
    """(directory, the part the rule sees, the part it does not).

    A dotfile with no extension ("*.bashrc") keeps its leading dot: treating it as an
    extension is how bulk renames silently turn .bashrc into a file called "bashrc".
    """
    directory, base = os.path.split(path.rstrip(os.sep))
    stem, dot, ext = base.rpartition(".")
    if not dot or not stem:                        # "README" or ".bashrc"
        stem, ext = base, ""
    if target == "name":
        return directory, stem, ("." + ext if ext else "")
    if target == "extension":
        return directory, ext, stem
    return directory, base, ""


def join_name(directory: str, new: str, rest: str, target: str) -> str:
    base = new + rest if target != "extension" else (rest + ("." + new if new else ""))
    return os.path.join(directory, base)


def build(paths: list[str], rule, target: str = "name") -> Plan:
    """Apply the rule to every path and check the result before anything moves."""
    if target not in ("name", "extension", "full"):
        raise RuleError(f"unknown target {target!r}")
    plan = Plan()
    seen: dict[str, str] = {}

    for index, path in enumerate(paths):
        directory, part, rest = split_name(path, target)
        try:
            new_part = rule.transform(part, index, path)
        except RuleError as e:
            plan.problems.append(f"{os.path.basename(path)}: {e}")
            continue

        if new_part != part:
            bad = FORBIDDEN & set(new_part)
            if bad:
                plan.problems.append(
                    f"{os.path.basename(path)}: the new name contains "
                    f"{', '.join(repr(c) for c in sorted(bad))}")
                continue

        dst = join_name(directory, new_part, rest, target)
        base = os.path.basename(dst)
        if not base or base in RESERVED:
            plan.problems.append(f"{os.path.basename(path)}: the new name would be empty")
            continue
        if not new_part and target == "name":
            # "report.txt" with the name rubbed out leaves ".txt": a valid filename, and
            # never what anyone meant — it is a hidden file with no name of its own.
            plan.problems.append(f"{os.path.basename(path)}: nothing would be left "
                                 f"of the name, only {base}")
            continue
        if len(base.encode("utf-8")) > 255:
            plan.problems.append(f"{os.path.basename(path)}: the new name is too long")
            continue

        lowered = dst if _case_sensitive(directory) else dst.lower()
        if lowered in seen and seen[lowered] != path:
            plan.problems.append(
                f"{os.path.basename(path)} and {os.path.basename(seen[lowered])} "
                f"would both become {base}")
            continue
        seen[lowered] = path
        plan.renames.append(Rename(path, dst))

    _check_existing(plan)
    return plan


def _case_sensitive(directory: str) -> bool:
    """Linux filesystems are, but a mounted NTFS or exFAT share is not."""
    return os.name == "posix" and "/run/media" not in directory


def _check_existing(plan: Plan) -> None:
    """Refuse to write over a file that is not itself part of this rename."""
    sources = {os.path.abspath(r.src) for r in plan.renames}
    for r in plan.changes:
        target = os.path.abspath(r.dst)
        if not os.path.lexists(target) or target in sources:
            continue
        # On a case-insensitive filesystem — a mounted NTFS share, or Windows — the
        # target of a case-only rename "exists" because it *is* the source file.
        try:
            if os.path.samefile(target, r.src):
                continue
        except OSError:
            pass
        plan.problems.append(
            f"{os.path.basename(r.dst)} already exists and is not being renamed")


# ---------------------------------------------------------------- carrying it out

def execute(plan: Plan, journal_path: str | None = None) -> list[Rename]:
    """Do the renames, and leave behind enough to undo them.

    Renames go through temporary names first. Without that, swapping two names (a→b,
    b→a) or shifting a numbered series down by one destroys files halfway through,
    even though every individual step looked safe.
    """
    if not plan.ok:
        raise RuleError("; ".join(plan.problems))
    changes = plan.changes
    if not changes:
        return []

    stamp = f".obulkrename-{os.getpid()}-{int(time.time())}"
    done: list[Rename] = []
    staged: list[tuple[str, str]] = []
    try:
        for i, r in enumerate(changes):
            temp = os.path.join(os.path.dirname(r.src) or ".", f"{stamp}-{i}")
            os.rename(r.src, temp)
            staged.append((temp, r.dst))
        for temp, dst in staged:
            os.rename(temp, dst)
        done = list(changes)
    except OSError:
        # Put back whatever is still sitting under a temporary name.
        for (temp, dst), r in zip(staged, changes):
            if os.path.lexists(temp):
                try:
                    os.rename(temp, r.src)
                except OSError:
                    pass
        raise

    if journal_path:
        write_journal(journal_path, done)
    return done


def write_journal(path: str, renames: list[Rename]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"when": time.time(),
               "renames": [{"src": r.src, "dst": r.dst} for r in renames]}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def read_journal(path: str) -> list[Rename]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [Rename(r["src"], r["dst"]) for r in data.get("renames", [])
            if isinstance(r, dict) and "src" in r and "dst" in r]


def undo(renames: list[Rename]) -> Plan:
    """The last rename, backwards — checked the same way as any other plan."""
    plan = Plan(renames=[Rename(r.dst, r.src) for r in renames])
    missing = [r.src for r in plan.renames if not os.path.lexists(r.src)]
    if missing:
        plan.problems.append(
            f"{len(missing)} file(s) are no longer where the last rename left them")
    _check_existing(plan)
    return plan
