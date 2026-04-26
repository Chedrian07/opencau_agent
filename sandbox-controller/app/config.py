from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sandbox_image: str = "opencau-agent-sandbox:latest"
    sandbox_network: str = "opencau_agent_internal"
    sandbox_memory_limit: str = "2g"
    sandbox_cpus: float = Field(default=2.0, gt=0)
    sandbox_pids_limit: int = Field(default=512, ge=64)
    display_width: int = Field(default=1920, ge=1)
    display_height: int = Field(default=1080, ge=1)
    display_depth: int = Field(default=24, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
