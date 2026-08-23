"""
core/state.py — In-memory conversation state for a single running session.

This is deliberately dumb: a list of turns plus a couple of flags. Anything
that needs to survive a restart belongs in memory/, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Turn:
    role: Role
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionState:
    turns: list[Turn] = field(default_factory=list)
    session_id: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )

    def add_turn(self, role: Role, text: str) -> None:
        self.turns.append(Turn(role=role, text=text))

    def recent(self, max_turns: int) -> list[Turn]:
        """Most recent `max_turns` turns, oldest first."""
        if max_turns <= 0:
            return []
        return self.turns[-max_turns:]

    def reset(self) -> None:
        """Clear transient context. Does not touch persisted memory."""
        self.turns.clear()
