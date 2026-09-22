"""The Omarchy menu, reused rather than reinvented.

omarchy-menu-select and omarchy-menu-input drive the Quickshell picker the rest of
the system uses, so this plugin looks and behaves like everything else — and stays
themed automatically. When they are missing (someone running this outside Omarchy),
gum is tried next, and the last resort is a plain numbered prompt on the terminal.
"""
from __future__ import annotations

import os
import shutil
import subprocess


def _env() -> dict[str, str]:
    e = dict(os.environ)
    e.setdefault("WAYLAND_DISPLAY", "wayland-1")
    return e


def have_omarchy_menu() -> bool:
    return shutil.which("omarchy-menu-select") is not None


def select(prompt: str, rows: list[tuple[str, str, str]], width: int | None = None) -> str | None:
    """Pick one row, given as (glyph, label, subtext).

    Returns "label\\tsubtext" — the pair the caller keys its table on — or None when
    the user cancelled. A picker that could not open says so out loud instead of
    looking like a cancel, because nothing else on screen would explain it.
    """
    if have_omarchy_menu():
        options = ["\t".join(r) for r in rows]
        cmd = ["omarchy-menu-select", prompt, *options]
        if width:
            cmd += ["--", "--width", str(width)]
        r = subprocess.run(cmd, capture_output=True, env=_env(), check=False)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip()
            if err:
                notify("Bulk rename", f"The menu could not open: {err.splitlines()[-1]}")
            return None
        return r.stdout.decode("utf-8", "replace").strip("\n") or None

    plain = [f"{label}\t{sub}" for _, label, sub in rows]
    if shutil.which("gum"):
        r = subprocess.run(["gum", "filter", "--placeholder", prompt],
                           input="\n".join(plain).encode("utf-8"),
                           capture_output=True, env=_env(), check=False)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", "replace").strip("\n") or None

    return _ask_on_terminal(prompt, plain)


def _ask_on_terminal(prompt: str, options: list[str]) -> str | None:
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"{i:3}. {opt.replace(chr(9), '  —  ')}")
    try:
        answer = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return options[int(answer) - 1]
    return None


def ask(prompt: str, width: int | None = 500) -> str | None:
    """Ask for a line of text."""
    if shutil.which("omarchy-menu-input"):
        cmd = ["omarchy-menu-input", prompt]
        if width:
            cmd += ["--width", str(width)]
        r = subprocess.run(cmd, capture_output=True, env=_env(), check=False)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", "replace").strip("\n") or None

    if shutil.which("gum"):
        r = subprocess.run(["gum", "input", "--placeholder", prompt],
                           capture_output=True, env=_env(), check=False)
        return r.stdout.decode("utf-8", "replace").strip("\n") or None if r.returncode == 0 else None

    try:
        return input(f"{prompt}: ").strip() or None
    except (EOFError, KeyboardInterrupt):
        return None


def notify(title: str, body: str = "", urgency: str = "normal") -> None:
    """Omarchy's own notification when it is there, libnotify otherwise."""
    if shutil.which("omarchy-notification-send"):
        subprocess.run(["omarchy-notification-send", title, body],
                       capture_output=True, env=_env(), check=False)
        return
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-u", urgency, "-a", "Bulk Rename", title, body],
                       capture_output=True, env=_env(), check=False)
