"""Unit tests for app.config."""
from __future__ import annotations

from app.config import Settings


class TestSettings:
    def test_default_values(self):
        s = Settings()
        assert s.app_env == "development"
        assert s.app_port == 8000
        assert s.llm_provider == "stub"
        assert s.stt_backend == "faster-whisper"
        assert s.autopilot is False

    def test_cors_origins_from_string(self):
        s = Settings(cors_origins="http://localhost:3000, http://localhost:5173")
        assert s.cors_origins == ["http://localhost:3000", "http://localhost:5173"]

    def test_cors_origins_from_list(self):
        s = Settings(cors_origins=["http://a.com", "http://b.com"])
        assert s.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins_empty_string(self):
        s = Settings(cors_origins="")
        assert s.cors_origins == []

    def test_data_path_creates_dirs(self, tmp_path):
        s = Settings(data_dir=str(tmp_path / "test_data"))
        p = s.data_path
        assert p.exists()
        assert (p / "audio").exists()
