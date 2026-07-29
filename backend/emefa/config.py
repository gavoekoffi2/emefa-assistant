"""Environment-backed configuration for EMEFA."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    enrollment_code: str | None = None
    database_path: Path = Path("emefa.db")
    #: Where account emails point back to. Wrong here means verification and
    #: reset links land nowhere, so it is explicit rather than guessed from
    #: the incoming request — a Host header is attacker-controlled.
    public_base_url: str = "http://localhost:5173"
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
    vision_model: str = "google/gemini-2.5-flash-lite"
    voice_llm_token: SecretStr | None = None
    brief_hour: int | None = None
    #: Local hour for the end-of-day report; unset disables the evening job.
    evening_hour: int | None = None
    brief_email_to: str | None = None
    routine_timezone: str = "Africa/Lome"
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_voice_id: str | None = None
    livekit_url: str | None = None
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None
    livekit_agent_name: str = "emefa"
    livekit_token_ttl_seconds: int = 300
    livekit_worker_token: SecretStr | None = None
    voice_transport: Literal["elevenlabs", "livekit"] = "elevenlabs"
    #: Encrypts connected-account secrets at rest. Without it the vault
    #: refuses to store credentials rather than keeping them in clear.
    secret_key: SecretStr | None = None
    email_account: str | None = None
    himalaya_binary: str = "himalaya"
    himalaya_config: Path | None = None
    web_dist_path: Path | None = None

    model_config = SettingsConfigDict(
        env_prefix="EMEFA_",
        env_file=".env",
        extra="ignore",
    )
