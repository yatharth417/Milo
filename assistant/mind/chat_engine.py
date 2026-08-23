"""
mind/chat_engine.py — Conversational core.

Backend is llama-cpp-python (GGUF, local, GPU-offloadable) since that's the
runtime implied by the Q4 GGUF model choice in the plan. A MockBackend is
included so main.py and the orchestrator can be exercised end-to-end on a
machine without the actual weights or a GPU — useful for testing the
plumbing before the real model is wired in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

log = logging.getLogger(__name__)


@dataclass
class GenerationParams:
    max_tokens: int = 512
    temperature: float = 0.8
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    stream: bool = True


class Backend(Protocol):
    def generate(self, prompt: str, params: GenerationParams) -> Iterator[str]:
        """Yield response text incrementally (token/chunk at a time)."""
        ...


class LlamaCppBackend:
    """Real backend. Requires `llama-cpp-python` and a local GGUF file."""

    def __init__(self, model_path: Path, context_length: int, gpu_layers: int, threads: int):
        try:
            from llama_cpp import Llama  # imported lazily so the mock path has no hard dep
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python is not installed. Run `pip install llama-cpp-python` "
                "(with the appropriate CMAKE args for your GPU) or use the mock backend."
            ) from e

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model weights not found at {model_path}. Update model.path in "
                "config/assistant.yaml, or use the mock backend for testing."
            )

        log.info("Loading model from %s (gpu_layers=%d)", model_path, gpu_layers)
        self._llm = Llama(
            model_path=str(model_path),
            n_ctx=context_length,
            n_gpu_layers=gpu_layers,
            n_threads=threads,
            verbose=False,
        )

    def generate(self, prompt: str, params: GenerationParams) -> Iterator[str]:
        stream = self._llm(
            prompt,
            max_tokens=params.max_tokens,
            temperature=params.temperature,
            top_p=params.top_p,
            repeat_penalty=params.repeat_penalty,
            stream=True,
        )
        for chunk in stream:
            text = chunk["choices"][0]["text"]
            if text:
                yield text

    def unload(self) -> None:
        # llama-cpp-python frees resources on GC; explicit del helps it along
        # so VRAM is actually released before the next model loads.
        del self._llm

class OllamaBackend:
    """Talks to a local Ollama server instead of loading a GGUF directly."""

    def __init__(self, model_name: str, host: str = "http://localhost:11434"):
        try:
            import requests  # lazy so the mock path has no hard dependency
        except ImportError as e:
            raise RuntimeError(
                "requests is not installed (needed for the Ollama backend). "
                "Run `pip install requests` or use the mock backend."
            ) from e
        self._requests = requests
        self._model = model_name
        self._url = f"{host.rstrip('/')}/api/generate"

    def generate(self, prompt: str, params: GenerationParams) -> Iterator[str]:
        resp = self._requests.post(
            self._url,
            # (connect, read-between-chunks): a stalled server errors out
            # instead of hanging the REPL forever.
            timeout=(10, 120),
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": params.temperature,
                    "top_p": params.top_p,
                    "repeat_penalty": params.repeat_penalty,
                    "num_predict": params.max_tokens,
                },
            },
            stream=True,
        )
        import json
        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("response"):
                yield data["response"]
            if data.get("done"):
                break

    def unload(self) -> None:
        pass  # Ollama manages its own model lifecycle/unloading

class MockBackend:
    """
    Deterministic fake backend for testing the pipeline without real weights.
    Echoes a canned response so you can verify prompt building, streaming,
    state updates, and the terminal UI all work before the real model is
    wired in.
    """

    def generate(self, prompt: str, params: GenerationParams) -> Iterator[str]:
        reply = (
            "[mock backend] I don't have real weights loaded, but the "
            "pipeline reached generation. Prompt was "
            f"{len(prompt)} characters."
        )
        for word in reply.split(" "):
            yield word + " "

    def unload(self) -> None:
        pass


class ChatEngine:
    """Thin wrapper the orchestrator talks to — backend-agnostic."""

    def __init__(self, backend: Backend):
        self._backend = backend

    def generate_response(self, prompt: str, params: GenerationParams) -> str:
        return "".join(self.stream_response(prompt, params))

    def stream_response(self, prompt: str, params: GenerationParams) -> Iterator[str]:
        yield from self._backend.generate(prompt, params)

    def unload(self) -> None:
        unload_fn = getattr(self._backend, "unload", None)
        if unload_fn:
            unload_fn()


def build_prompt(system_prompt: str, memory_context: str, conversation: str) -> str:
    """
    Assemble the full prompt sent to the model.

    Kept as a plain string-formatting function (not a class) so it's easy
    to unit test and swap chat templates later without touching the engine.
    Uses a ChatML-ish structure — adjust to match whatever template Qwen2.5
    was instruction-tuned with if you change models.
    """
    parts = [f"<|im_start|>system\n{system_prompt}"]
    if memory_context.strip():
        parts.append(f"\n## Relevant memory\n{memory_context.strip()}")
    parts.append("<|im_end|>\n")
    parts.append(conversation)
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)
