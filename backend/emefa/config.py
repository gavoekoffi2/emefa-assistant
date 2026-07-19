"""Environment-backed configuration for EMEFA."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    enrollment_code: str | None = None
    database_path: Path = Path("emefa.db")
    max_devices: int = 3
    cookie_secure: bool = True
    session_max_age_seconds: int = 2_592_000
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = "deepseek-v4-flash"
    openai_api_key: SecretStr | None = None
    realtime_model: str = "gpt-realtime-2.1"
    realtime_voice: str = "marin"
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_agent_id: str | None = None
    web_dist_path: Path | None = None

    model_config = SettingsConfigDict(
        env_prefix="EMEFA_",
        env_file=".env",
        extra="ignore",
    )
