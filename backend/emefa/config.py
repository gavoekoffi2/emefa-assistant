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
    #: Extract durable facts from each exchange as it happens. Costs one small
    #: LLM call per substantial turn; set false to rely on consolidation alone.
    memory_live_extraction: bool = True
    #: Local hour for the nightly consolidation pass. None disables it.
    memory_consolidation_hour: int | None = 3
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_agent_id: str | None = None
    email_account: str | None = None
    himalaya_binary: str = "himalaya"
    himalaya_config: Path | None = None
    web_dist_path: Path | None = None
    #: Provider prices, in USD per million tokens. Left at zero because a
    #: guessed price produces a spend report the owner would act on and that
    #: is quietly wrong; token counters work regardless.
    price_per_mtok_in: float = 0.0
    price_per_mtok_out: float = 0.0
    #: Daily token ceilings for work EMEFA starts on her own initiative
    #: (CLAUDE.md §34). The user's own chat and voice are not capped here.
    daily_token_limit_extraction: int = 200_000
    daily_token_limit_consolidation: int = 200_000
    daily_token_limit_proactive: int = 100_000
    #: Minutes between proactive collection passes. None disables them.
    proactive_interval_minutes: int | None = 60
    #: Instance ceiling on unprompted autonomy (see AutonomyLevel). Default 2
    #: = PREPARE: EMEFA may draft on her own, never deliver.
    max_autonomy_level: int = 2
    #: Skill catalogue directory. Defaults to the one shipped with the
    #: package; point it elsewhere to add skills without a redeploy.
    skills_catalogue_path: Path | None = None

    model_config = SettingsConfigDict(
        env_prefix="EMEFA_",
        env_file=".env",
        extra="ignore",
    )
