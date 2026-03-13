import logging
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, model_validator
from typing import List

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # LLM — no hardcoded default URL (#108): must be set in .env / environment
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_default_model: str = "gpt-4o"
    llm_council_models: str = "gpt-4o,gpt-4o,gpt-4o"
    llm_chairman_model: str = "gpt-4o"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False  # (#108) safe default; set DEBUG=true in dev .env

    database_url: str = "sqlite:///./wargame.db"

    # CORS
    allowed_origins: str = "*"

    # Supabase (for auth + RLS)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _validate_required(self) -> "Settings":
        """Raise at startup if critical env vars are missing (#108)."""
        if not self.llm_base_url:
            raise ValueError(
                "LLM_BASE_URL is not set. "
                "Add LLM_BASE_URL=https://<your-llm-proxy>/v1 to your .env file."
            )
        if not self.llm_api_key:
            logger.warning(
                "LLM_API_KEY is empty — LLM calls will fail unless the endpoint allows unauthenticated access."
            )
        return self

    @property
    def council_models_list(self) -> List[str]:
        return [m.strip() for m in self.llm_council_models.split(",") if m.strip()]


settings = Settings()
