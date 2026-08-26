"""
voice/pipeline.py — Glue between microphone/speakers and the chat loop.

Builds the STT/TTS/recorder pieces from config and turns their failures
into ordinary messages. Deliberately knows nothing about intents, memory,
or generation — routing stays in main.py untouched, so spoken input goes
through exactly the same pipeline as typed input.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class VoiceInitError(RuntimeError):
    """Voice can't start at all (missing models/packages). Fatal for --voice."""


class VoiceError(RuntimeError):
    """A runtime voice problem (mic failure, decode error) for one turn."""


class VoicePipeline:
    def __init__(self, voice_cfg):
        # Imported lazily by callers; construct eagerly so missing models are
        # reported once, up front, instead of exploding mid-conversation.
        from voice.recorder import PushToTalkRecorder
        from voice.stt import Transcriber
        from voice.tts import Speaker

        try:
            self._recorder = PushToTalkRecorder()
            self._transcriber = Transcriber(voice_cfg.stt_model_dir)
            self._speaker = Speaker(voice_cfg.tts_model_dir)
        except Exception as e:
            raise VoiceInitError(str(e)) from e
        log.info("Voice pipeline ready")

    def listen(self) -> str:
        """
        Record one push-to-talk utterance and return its text ('' if silent).

        Raises EOFError when stdin closes so the caller can end the
        session; other problems come back as VoiceError for this turn only.
        """
        from voice.recorder import RecorderError
        from voice.stt import STTError

        try:
            audio = self._recorder.record()
            return self._transcriber.transcribe(audio)
        except EOFError:
            raise
        except RecorderError as e:
            raise VoiceError(str(e)) from e
        except STTError as e:
            raise VoiceError(str(e)) from e

    def say(self, text: str) -> None:
        """Speak text aloud; speech problems degrade to a notice, not a crash."""
        from voice.tts import TTSError

        try:
            self._speaker.speak(text)
        except TTSError as e:
            print(f"(speech unavailable this turn: {e})")
