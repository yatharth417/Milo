"""
core/model_lifecycle.py — Model lifecycle manager.

Per the build plan: avoid multiple simultaneously loaded LLMs in the MVP.
This module exists specifically so that rule has somewhere to live, instead
of load/unload being scattered ad hoc through mind/chat_engine.py. When a
second model shows up later (gatekeeper, executor, TTS), it registers here
and this manager enforces the "only what's needed is resident" policy.

For the MVP there is exactly one slot: the conversational model.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)


class ModelLifecycleManager:
    """
    Tracks which model is currently loaded and mediates load/unload calls.

    Usage:
        manager = ModelLifecycleManager()
        manager.register("chat", load_fn=load_qwen, unload_fn=unload_qwen)
        model = manager.acquire("chat")
        ...
        manager.release("chat")   # optional in MVP (single model stays hot)
    """

    def __init__(self) -> None:
        self._loaders: dict[str, Callable[[], object]] = {}
        self._unloaders: dict[str, Callable[[object], None]] = {}
        self._loaded: dict[str, object] = {}
        self._active_slot: Optional[str] = None

    def register(
        self,
        name: str,
        load_fn: Callable[[], object],
        unload_fn: Callable[[object], None],
    ) -> None:
        self._loaders[name] = load_fn
        self._unloaders[name] = unload_fn

    def acquire(self, name: str) -> object:
        """
        Return a loaded model instance for `name`, loading it if needed.

        MVP policy: only one model may be resident at a time. If a
        different model is currently loaded, it is unloaded first. This
        keeps VRAM behavior predictable and explicit rather than implicit.
        """
        if name not in self._loaders:
            raise KeyError(f"No model registered under name '{name}'")

        if self._active_slot == name and name in self._loaded:
            return self._loaded[name]

        if self._active_slot is not None and self._active_slot != name:
            log.info("Swapping model: unloading '%s' to load '%s'", self._active_slot, name)
            self.release(self._active_slot)

        log.info("Loading model '%s'", name)
        instance = self._loaders[name]()
        self._loaded[name] = instance
        self._active_slot = name
        return instance

    def release(self, name: str) -> None:
        if name not in self._loaded:
            return
        log.info("Unloading model '%s'", name)
        self._unloaders[name](self._loaded[name])
        del self._loaded[name]
        if self._active_slot == name:
            self._active_slot = None

    def release_all(self) -> None:
        for name in list(self._loaded.keys()):
            self.release(name)

    @property
    def active_slot(self) -> Optional[str]:
        return self._active_slot
