"""Terminal UI helpers: prompts with validation loops, headings, pagination."""
from __future__ import annotations

import os
import re
import sys
from datetime import date

from .config import PAGE_SIZE
from .log import LOG
from .models import parse_date

if os.name == "nt":
    os.system("")  # enables ANSI escape codes on Windows 10+
USE_COLOR = sys.stdout.isatty()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def ok(msg): LOG.info(msg)
def warn(msg): LOG.warning(msg)
def err(msg): LOG.error(msg)
def heading(msg): print("\n" + c(msg, "1;36") + "\n" + c("─" * len(msg), "36"))


class Cancel(Exception):
    """Raised when the user types /cancel during a prompt."""


def ask(label: str) -> str:
    value = input(label).strip()
    if value.lower() == "/cancel":
        raise Cancel
    return value


def ask_text(label: str, pattern: re.Pattern, hint: str) -> str:
    while True:
        value = " ".join(ask(label).split())
        if pattern.fullmatch(value):
            return value
        err(hint)


def ask_int(label: str, lo: int, hi: int) -> int:
    while True:
        raw = ask(label)
        try:
            value = int(raw)
        except ValueError:
            err(f"'{raw}' is not a whole number. Enter a number from {lo} to {hi}.")
            continue
        if lo <= value <= hi:
            return value
        err(f"{value} is out of range. Enter a number from {lo} to {hi}.")


def ask_date(label: str) -> date:
    while True:
        raw = ask(label) or date.today().isoformat()
        try:
            d = parse_date(raw)
        except ValueError as e:
            err(str(e))
            continue
        if d > date.today():
            err("Date cannot be in the future.")
            continue
        return d


def ask_yes(label: str) -> bool:
    while True:
        a = ask(label + " [y/n]: ").lower()
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        err("Please answer y or n.")


def pause():
    if sys.stdin.isatty():
        input(c("\n  Press Enter to continue...", "2"))


def paginate(rows, formatter):
    """Print a table in pages with a repeated header."""
    if not rows:
        print("  (no records)")
        return
    for start in range(0, len(rows), PAGE_SIZE):
        chunk = rows[start:start + PAGE_SIZE]
        print(formatter(chunk))
        end = start + len(chunk)
        print(c(f"  Showing {start + 1}-{end} of {len(rows)}", "2"))
        if end < len(rows) and sys.stdin.isatty():
            if input("  Enter = next page, q = stop: ").strip().lower() == "q":
                break
