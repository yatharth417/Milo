"""
voice/recorder.py — Push-to-talk microphone capture.

Records 16 kHz mono float32 from the default input device. The flow is
deliberately manual (Enter to start, Enter to stop) so no VAD is needed
in this slice: the user, not an algorithm, decides where the utterance
begins and ends.
"""

from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # what both the STT model and sherpa-onnx expect


class RecorderError(RuntimeError):
    """Raised when the microphone can't be opened or the stream fails."""


class PushToTalkRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self._sample_rate = sample_rate

    def record(self) -> np.ndarray:
        """
        Block until Enter is pressed twice: once to start, once to stop.

        Audio accumulates in a stream callback while the main thread waits
        on input(), which stays portable (no raw keyboard polling) and
        safe (list.append is atomic under the GIL). Returns float32 mono
        samples; may be empty if the user stopped immediately.
        Raises EOFError when stdin closes so the caller can end the session.
        """
        # ASCII-only prompts: some Windows consoles can't print fancy glyphs.
        try:
            input("[voice] press Enter, then speak")
        except EOFError:
            raise
        except KeyboardInterrupt:
            return np.zeros(0, dtype=np.float32)

        chunks: list[np.ndarray] = []

        def callback(indata, frames, time_info, status):  # noqa: ANN001 (sd API)
            if status:
                log.warning("Microphone stream status: %s", status)
            chunks.append(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                callback=callback,
            ):
                try:
                    input("[voice] recording... press Enter to stop")
                except EOFError:
                    pass  # stdin closed mid-recording: stop and keep what we have
        except sd.PortAudioError as e:
            raise RecorderError(f"microphone unavailable: {e}") from e

        audio = (
            np.concatenate(chunks).reshape(-1)
            if chunks
            else np.zeros(0, dtype=np.float32)
        )
        log.info("Recorded %.1fs of audio", len(audio) / self._sample_rate)
        return audio
