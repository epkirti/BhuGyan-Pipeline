"""Central configuration, loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database / cache
    database_url: str = "postgresql://bhugyan:bhugyan@localhost:5432/bhugyan"
    redis_url: str = "redis://localhost:6379/0"

    # LLM (empty key -> deterministic offline stub)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Embeddings
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # Pipeline thresholds (report §3)
    dedupe_similarity_threshold: float = 0.95
    place_resolve_score_cutoff: int = 85

    # Logging
    log_level: str = "INFO"
    run_log_dir: Path = PROJECT_ROOT / "run_logs"

    @property
    def has_llm(self) -> bool:
        return bool(self.groq_api_key.strip())


settings = Settings()
