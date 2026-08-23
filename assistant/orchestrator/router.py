"""
orchestrator/router.py — Basic intent routing for Phase 0.

Deliberately minimal: three buckets, no ML classifier yet. Per the build
plan's Rule 4 (deterministic systems handle deterministic work), even this
simple routing uses cheap heuristics rather than burning a model call just
to decide "is this an action request?" A real classifier/gatekeeper model
can replace this function later without changing its signature.
"""

from __future__ import annotations

from enum import Enum

_ACTION_PREFIXES = ("open ", "run ", "launch ", "delete ", "move ", "organize ")
_MEMORY_MARKERS = ("remember", "recall", "what do you know about", "forget that")


class Intent(str, Enum):
    CONVERSATION = "conversation"
    MEMORY = "memory"
    ACTION = "action"


def classify_intent(user_input: str) -> Intent:
    text = user_input.strip().lower()

    if any(text.startswith(p) for p in _ACTION_PREFIXES):
        return Intent.ACTION

    if any(marker in text for marker in _MEMORY_MARKERS):
        return Intent.MEMORY

    return Intent.CONVERSATION

_REMEMBER_PREFIXES = ("remember that ", "remember ")


def extract_remember_fact(user_input: str) -> str | None:
    """
    If the input is an explicit "remember that X" / "remember X" command,
    return the fact text (X). Otherwise None.
    """
    text = user_input.strip()
    lowered = text.lower()
    for prefix in _REMEMBER_PREFIXES:
        if lowered.startswith(prefix):
            fact = text[len(prefix):].strip()
            return fact or None
    return None