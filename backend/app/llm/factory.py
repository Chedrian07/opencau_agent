from __future__ import annotations

from app.config import Settings
from app.llm.base import LLMAdapter
from app.llm.function_computer import FunctionComputerAdapter
from app.llm.mock import MockComputerAdapter
from app.llm.openai_computer import OpenAIComputerAdapter
from app.llm.stateless_function import StatelessFunctionAdapter


def build_adapter(settings: Settings) -> LLMAdapter:
    if settings.llm_profile == "mock":
        return MockComputerAdapter(settings)
    if settings.llm_state_mode == "manual":
        return StatelessFunctionAdapter(settings)
    if settings.llm_tool_mode == "openai_computer":
        return OpenAIComputerAdapter(settings)
    return FunctionComputerAdapter(settings)
