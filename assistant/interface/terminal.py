"""
interface/terminal.py — Lowest-cost interface, per Phase 0 of the build plan.
"""

from __future__ import annotations

import sys


def display_message(sender: str, text: str, end: str = "\n") -> None:
    print(f"{sender}: {text}", end=end, flush=True)


def stream_token(token: str) -> None:
    """Print a single generated chunk without a newline, for streaming output."""
    print(token, end="", flush=True)


def get_user_input(prompt: str = "you: ") -> str:
    try:
        return input(prompt)
    except EOFError:
        return "/exit"


def show_typing_indicator() -> None:
    print("assistant: ", end="", flush=True)


def newline() -> None:
    print()


def is_interactive() -> bool:
    return sys.stdin.isatty()
