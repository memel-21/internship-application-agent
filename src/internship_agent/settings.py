"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the local application."""

    model_config = SettingsConfigDict(env_prefix="INTERNSHIP_AGENT_", env_file=".env")

    demo_mode: bool = True
    database_url: str = "sqlite:///data/internship_agent.db"
    candidate_profile_path: Path = Field(default=Path("config/candidate_profile.json"))
