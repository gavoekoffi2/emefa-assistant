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
    activation_max_failures: int = 5
    activation_window_seconds: int = 900
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = "deepseek-v4-flash"
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "deepseek/deepseek-chat"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    voice_llm_token: SecretStr | None = None
    brief_hour: int | None = None
    brief_email_to: str | None = None
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_agent_id: str | None = None
    email_account: str | None = None
    himalaya_binary: str = "himalaya"
    himalaya_config: Path | None = None
    web_dist_path: Path | None = None

    model_config = SettingsConfigDict(
        env_prefix="EMEFA_",
        env_file=".env",
        extra="ignore",
    )
