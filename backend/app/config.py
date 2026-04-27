from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProfile = Literal[
    "openai-native",
    "lmstudio-responses",
    "vllm-responses",
    "ollama-stateless",
    "mock",
]
LLMToolMode = Literal["openai_computer", "function_computer"]
LLMStateMode = Literal["server", "manual"]
ScreenshotDetail = Literal["original", "low", "high"]


_PROFILE_ALIASES: dict[str, LLMProfile] = {
    "openai": "openai-native",
    "openai-native": "openai-native",
    "lmstudio": "lmstudio-responses",
    "lmstudio-responses": "lmstudio-responses",
    "lm-studio": "lmstudio-responses",
    "lm_studio": "lmstudio-responses",
    "vllm": "vllm-responses",
    "vllm-responses": "vllm-responses",
    "ollama": "ollama-stateless",
    "ollama-stateless": "ollama-stateless",
    "mock": "mock",
}


def _str_to_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_profile(value: str) -> str:
    cleaned = value.strip().lower().replace(" ", "")
    return _PROFILE_ALIASES.get(cleaned, value)


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
    screenshot_retention_hours: int = Field(default=24, ge=1, le=720)

    llm_profile: LLMProfile = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1"
    llm_tool_mode: LLMToolMode = "openai_computer"
    llm_state_mode: LLMStateMode = "server"
    llm_supports_vision: bool = True
    llm_supports_tool_calls: bool = True
    llm_history_window: int = Field(default=12, ge=2, le=64)
    llm_request_timeout_sec: float = Field(default=120.0, gt=0)

    max_agent_steps: int = Field(default=20, ge=1, le=200)
    agent_timeout_sec: int = Field(default=600, ge=1)
    action_timeout_sec: int = Field(default=10, ge=1)
    screenshot_detail: ScreenshotDetail = "original"
    repeated_action_threshold: int = Field(default=3, ge=2, le=10)
    sandbox_idle_timeout_sec: int = Field(default=1800, ge=60, le=86_400)
    cleanup_interval_sec: int = Field(default=60, ge=5, le=3600)

    @field_validator("llm_profile", mode="before")
    @classmethod
    def _normalize_llm_profile(cls, value: object) -> object:
        if isinstance(value, str):
            return _normalize_profile(value)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def is_mock_profile(self) -> bool:
        return self.llm_profile == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
