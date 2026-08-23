"""
orchestrator/actions.py — Whitelisted "open <app>" actions.

The whitelist in config/actions.yaml is the entire security boundary:
user text can only ever select a key that already exists there, never an
arbitrary command. Anything else is refused without executing anything.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_ACTIONS_PATH = Path("config/actions.yaml")

_OPEN_PREFIXES = ("open ",)


def load_action_whitelist(path: str | Path = _ACTIONS_PATH) -> dict:
    """
    Read the name -> command whitelist from actions.yaml.

    A missing or malformed file degrades to an empty whitelist instead of
    crashing the chat loop — every launch then just answers "not
    whitelisted", which is the safe direction to fail in.
    """
    path = Path(path)
    if not path.exists():
        log.warning("Action whitelist not found: %s", path)
        return {}

    with path.open("r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            log.error("Malformed action whitelist %s: %s", path, e)
            return {}

    if not isinstance(raw, dict):
        log.error("Action whitelist %s must be a mapping of name -> command list", path)
        return {}
    return raw


def extract_action(user_input: str) -> str | None:
    """Pull the target app name out of an "open <app>" command."""
    text = user_input.strip()
    lowered = text.lower()
    for prefix in _OPEN_PREFIXES:
        if lowered.startswith(prefix):
            app_name = text[len(prefix):].strip().strip("!?.,").lower()
            return app_name or None
    return None


def execute_action(app_name: str, whitelist: dict) -> str:
    """
    Launch a whitelisted app and return a human-readable result.

    User text picks a key, never a process. Launch failures (bad path,
    permissions) come back as plain text so a stale path in the YAML can't
    take down the chat loop.
    """
    if app_name not in whitelist:
        known = ", ".join(sorted(whitelist)) or "(none configured)"
        return f"'{app_name}' isn't in my whitelist. Apps I can open: {known}."

    command = whitelist[app_name]
    if not isinstance(command, list) or not command:
        return f"The entry for '{app_name}' in config/actions.yaml should be a non-empty list of arguments."

    try:
        # List form, no shell: the YAML entry goes to the OS verbatim as
        # argv, and Popen returns immediately rather than waiting for the
        # app to close.
        subprocess.Popen(command)
    except FileNotFoundError:
        return (
            f"'{app_name}' is whitelisted, but {command[0]} wasn't found on this "
            "machine — update its path in config/actions.yaml."
        )
    except OSError as e:
        return f"Tried to open '{app_name}' but it failed: {e}"

    return f"Opening {app_name}."
