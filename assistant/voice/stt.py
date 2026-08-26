"""
voice/stt.py — Offline speech-to-text via sherpa-onnx.

Whisper small.en (English-only), CPU-only, fully local: audio never
leaves the machine. Chosen over the smaller zipformer model for its
documented accuracy on Indian-English accents; push-to-talk means the
few extra seconds of non-streaming decode are acceptable.

Files are discovered by pattern rather than hardcoded names so the exact
size prefixes in the official archive (small.en-encoder.onnx, ...) don't
matter here. When both fp32 and int8 exist, sorted() picks int8 — the
faster CPU variant.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000  # Whisper's native input rate


class STTError(RuntimeError):
    """Raised when the STT model is missing/unreadable or decoding fails."""


class Transcriber:
    """float32 mono samples at 16 kHz -> transcribed text."""

    def __init__(self, model_dir: str | Path):
        model_dir = Path(model_dir)
        try:
            import sherpa_onnx
        except ImportError as e:
            raise STTError(
                "sherpa-onnx is not installed. Run: pip install sherpa-onnx"
            ) from e

        def find(pattern: str) -> Path:
            matches = sorted(model_dir.rglob(pattern))
            if not matches:
                raise STTError(
                    f"No '{pattern}' found under {model_dir}. "
                    "Download the Whisper STT model archive into that folder "
                    "and extract it."
                )
            return matches[0]

        try:
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(find("*encoder*.onnx")),
                decoder=str(find("*decoder*.onnx")),
                tokens=str(find("*tokens.txt")),
                num_threads=2,
            )
        except Exception as e:
            raise STTError(f"failed to load STT model from {model_dir}: {e}") from e
        log.info("STT ready (whisper from %s)", model_dir)

    def transcribe(self, samples: np.ndarray, sample_rate: int = _SAMPLE_RATE) -> str:
        """
        Transcribe float32 mono samples. Empty input -> ''.

        Non-16k rates are accepted here because sherpa-onnx resamples
        internally; the mic path always feeds 16k.
        """
        if samples.size == 0:
            return ""
        try:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            self._recognizer.decode_stream(stream)
            text = stream.result.text.strip()
        except Exception as e:
            raise STTError(f"transcription failed: {e}") from e
        log.info("STT result: %r", text)
        return text
