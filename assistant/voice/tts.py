"""
voice/tts.py — Local Piper/VITS speech synthesis via sherpa-onnx.

Renders replies to audio entirely on CPU (the GPU stays reserved for
Ollama) and plays through the default output device. Playback blocks
until finished, so the assistant never talks over its own next turn.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class TTSError(RuntimeError):
    """Raised when the TTS model is missing/unreadable or synthesis fails."""


class Speaker:
    def __init__(self, model_dir: str | Path):
        model_dir = Path(model_dir)
        try:
            import sherpa_onnx
        except ImportError as e:
            raise TTSError(
                "sherpa-onnx is not installed. Run: pip install sherpa-onnx"
            ) from e

        def find(pattern: str) -> Path:
            matches = sorted(model_dir.rglob(pattern))
            if not matches:
                raise TTSError(
                    f"No '{pattern}' found under {model_dir}. "
                    "Download the TTS voice archive into that folder and extract it."
                )
            return matches[0]

        voice = find("*.onnx")
        espeak_dir = find("espeak-ng-data")
        try:
            # 1.13.x API: nested config objects instead of the old
            # OfflineTts.from_vits() shortcut.
            vits_cfg = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(voice),
                tokens=str(find("tokens.txt")),
                data_dir=str(espeak_dir),
            )
            model_cfg = sherpa_onnx.OfflineTtsModelConfig(
                vits=vits_cfg,
                num_threads=2,  # CPU synthesis; GPU stays reserved for Ollama
            )
            self._tts = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=model_cfg))
        except Exception as e:
            raise TTSError(f"failed to load TTS voice from {model_dir}: {e}") from e
        log.info("TTS ready (%s)", voice.name)

    def speak(self, text: str) -> None:
        """Synthesize and play text aloud. Errors surface as TTSError."""
        if not text.strip():
            return
        try:
            import sounddevice as sd

            audio = self._tts.generate(text, sid=0, speed=1.0)
            if len(audio.samples) == 0:
                raise TTSError("synthesizer produced no audio")
            sd.play(audio.samples, audio.sample_rate)
            sd.wait()  # block so the next turn can't start mid-sentence
        except TTSError:
            raise
        except Exception as e:
            raise TTSError(f"playback failed: {e}") from e
