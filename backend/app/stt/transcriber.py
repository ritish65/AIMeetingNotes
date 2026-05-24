"""Real-time streaming speech-to-text transcriber.

Consumes chunks of 16kHz linear PCM audio, buffers them, and streams 
increments back. Uses faster-whisper locally or OpenAI's Whisper API.
"""
from __future__ import annotations

import io
import wave
from typing import Iterator

import numpy as np
from loguru import logger

from ..config import settings


class BaseTranscriber:
    def transcribe_chunk(self, pcm_bytes: bytes) -> str:
        """Transcribe a chunk of 16kHz mono 16-bit PCM audio."""
        raise NotImplementedError


class FasterWhisperTranscriber(BaseTranscriber):
    def __init__(self) -> None:
        try:
            from faster_whisper import WhisperModel

            logger.info(
                "Initializing local faster-whisper model: {} ({})",
                settings.whisper_model,
                settings.whisper_device,
            )
            self.model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
        except Exception as e:
            logger.error("Failed to load local Whisper: {}", e)
            self.model = None

    def transcribe_chunk(self, pcm_bytes: bytes) -> str:
        if not self.model or len(pcm_bytes) < 320:
            return ""
        # Convert 16-bit PCM bytes to float32 normalized array
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        try:
            segments, _ = self.model.transcribe(audio_np, beam_size=1, language="en")
            texts = [seg.text for seg in segments]
            return " ".join(texts).strip()
        except Exception as e:
            logger.error("Local Whisper transcription failed: {}", e)
            return ""


class OpenAIWhisperTranscriber(BaseTranscriber):
    def transcribe_chunk(self, pcm_bytes: bytes) -> str:
        if not settings.openai_api_key or len(pcm_bytes) < 320:
            return ""
        try:
            import openai

            client = openai.Client(api_key=settings.openai_api_key)

            # Package RAW 16kHz PCM bytes into a standard WAV container in memory
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_bytes)
            wav_buf.seek(0)
            wav_buf.name = "audio.wav"

            res = client.audio.transcriptions.create(
                model="whisper-1",
                file=wav_buf,
                language="en",
            )
            return res.text.strip()
        except Exception as e:
            logger.error("OpenAI Whisper API transcription failed: {}", e)
            return ""


class StubTranscriber(BaseTranscriber):
    def transcribe_chunk(self, pcm_bytes: bytes) -> str:
        return "[Placeholder live transcript segment]"


_transcriber_instance: BaseTranscriber | None = None


def get_transcriber() -> BaseTranscriber:
    global _transcriber_instance
    if _transcriber_instance is not None:
        return _transcriber_instance

    backend = (settings.stt_backend or "stub").lower()
    if backend == "faster-whisper":
        _transcriber_instance = FasterWhisperTranscriber()
        if getattr(_transcriber_instance, "model", None) is None:
            logger.warning("Local faster-whisper not available; falling back to stub.")
            _transcriber_instance = StubTranscriber()
    elif backend == "openai":
        _transcriber_instance = OpenAIWhisperTranscriber()
    else:
        _transcriber_instance = StubTranscriber()

    return _transcriber_instance
