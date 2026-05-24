"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret: str = "change-me"
    database_url: str = "sqlite+aiosqlite:///./pmia.db"
    data_dir: str = "./data"
    log_level: str = "INFO"
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # LLM
    llm_provider: str = "stub"  # openai | anthropic | groq | stub
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"
    # Groq (OpenAI-compatible API)
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # STT
    stt_backend: str = "faster-whisper"  # faster-whisper | openai | stub
    whisper_model: str = "base.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "pmia_meetings"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # HIL
    autopilot: bool = False

    # Tools
    todoist_token: str | None = None
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_refresh_token: str | None = None
    gmail_from: str | None = None
    gcal_client_id: str | None = None
    gcal_client_secret: str | None = None
    gcal_refresh_token: str | None = None
    gcal_calendar_id: str = "primary"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        (p / "audio").mkdir(parents=True, exist_ok=True)
        return p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
