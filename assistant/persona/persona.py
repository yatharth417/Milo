"""
persona/persona.py — Load a persona definition and build the system prompt.

Personas are plain Markdown files under persona/personas/<name>.md so a
human can open and edit them directly, per the "human-readable, no
black-box" principle from the build plan.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"version:\s*(\d+)")


@dataclass
class Persona:
    name: str
    version: int
    body: str  # full markdown content, minus the metadata comment block


class PersonaError(Exception):
    pass


def load_persona(name: str, personas_dir: str | Path = "persona/personas") -> Persona:
    personas_dir = Path(personas_dir)
    path = personas_dir / f"{name}.md"
    if not path.exists():
        raise PersonaError(f"Persona '{name}' not found at {path}")

    text = path.read_text(encoding="utf-8")
    version_match = _VERSION_RE.search(text)
    version = int(version_match.group(1)) if version_match else 1

    log.info("Loaded persona '%s' (version %d)", name, version)
    return Persona(name=name, version=version, body=text)


def build_system_prompt(persona: Persona, current_time: datetime | None = None) -> str:
    """
    Assemble the final system prompt: persona body + dynamic context
    (current time, for now). Memory context gets injected separately by
    the orchestrator, not baked in here, so this stays a pure function of
    the persona.
    """
    now = current_time or datetime.now()
    time_str = now.strftime("%A, %B %d, %Y — %H:%M")

    return (
        f"{persona.body.strip()}\n\n"
        "---\n\n"
        f"## Current context\n"
        f"The current date/time is: {time_str}\n"
    )
