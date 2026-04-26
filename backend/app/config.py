from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    sandbox_controller_url: str = "http://sandbox-controller:8100"
    display_width: int = Field(default=1920, ge=1)
    display_height: int = Field(default=1080, ge=1)
    display_depth: int = Field(default=24, ge=1)
    redis_url: str = "redis://redis:6379/0"
    sqlite_path: str = "/data/opencau-agent.sqlite"
    screenshot_dir: str = "/data/screenshots"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
