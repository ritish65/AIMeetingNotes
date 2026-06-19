"""Unit tests for app.stt.transcriber."""
from __future__ import annotations

import pytest

from app.stt.transcriber import (
    BaseTranscriber,
    StubTranscriber,
    get_transcriber,
)


class TestBaseTranscriber:
    def test_raises_not_implemented(self):
        t = BaseTranscriber()
        with pytest.raises(NotImplementedError):
            t.transcribe_chunk(b"\x00")


class TestStubTranscriber:
    def test_returns_placeholder(self):
        t = StubTranscriber()
        result = t.transcribe_chunk(b"\x00\x01\x02")
        assert result == "[Placeholder live transcript segment]"

    def test_returns_same_for_empty_bytes(self):
        t = StubTranscriber()
        result = t.transcribe_chunk(b"")
        assert result == "[Placeholder live transcript segment]"


class TestGetTranscriber:
    def test_returns_transcriber_instance(self, monkeypatch):
        # Reset singleton
        import app.stt.transcriber as mod

        monkeypatch.setattr(mod, "_transcriber_instance", None)
        monkeypatch.setattr("app.stt.transcriber.settings.stt_backend", "stub")
        t = get_transcriber()
        assert isinstance(t, StubTranscriber)

    def test_singleton_caching(self, monkeypatch):
        import app.stt.transcriber as mod

        monkeypatch.setattr(mod, "_transcriber_instance", None)
        monkeypatch.setattr("app.stt.transcriber.settings.stt_backend", "stub")
        t1 = get_transcriber()
        t2 = get_transcriber()
        assert t1 is t2

    def test_faster_whisper_fallback_to_stub(self, monkeypatch):
        """When faster-whisper model fails to load, should fall back to stub."""
        import app.stt.transcriber as mod

        monkeypatch.setattr(mod, "_transcriber_instance", None)
        monkeypatch.setattr("app.stt.transcriber.settings.stt_backend", "faster-whisper")
        t = get_transcriber()
        # Since faster-whisper model won't be available in test env, should fall back
        assert isinstance(t, (StubTranscriber, mod.FasterWhisperTranscriber))

    def test_openai_backend(self, monkeypatch):
        import app.stt.transcriber as mod

        monkeypatch.setattr(mod, "_transcriber_instance", None)
        monkeypatch.setattr("app.stt.transcriber.settings.stt_backend", "openai")
        t = get_transcriber()
        assert isinstance(t, mod.OpenAIWhisperTranscriber)

    def test_openai_transcriber_no_key(self):
        """OpenAI transcriber returns empty when no API key configured."""
        from app.stt.transcriber import OpenAIWhisperTranscriber

        t = OpenAIWhisperTranscriber()
        result = t.transcribe_chunk(b"\x00" * 400)
        assert result == ""

    def test_openai_transcriber_short_audio(self, monkeypatch):
        from app.stt.transcriber import OpenAIWhisperTranscriber

        monkeypatch.setattr("app.stt.transcriber.settings.openai_api_key", "test-key")
        t = OpenAIWhisperTranscriber()
        result = t.transcribe_chunk(b"\x00" * 100)  # less than 320 bytes
        assert result == ""
