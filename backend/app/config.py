from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    PISTON_URL: str = "http://localhost:2000/api/v2/execute"
    OPENAI_API_KEY: Optional[str] = ""
    # LLM_BASE_URL: str = "https://api.openai.com/v1"
    # LLM_MODEL: str = "gpt-4o"

    LLM_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    LLM_MODEL: str = "gemini-3.6-flash"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]
