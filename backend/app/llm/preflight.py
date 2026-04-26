from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.config import Settings


PreflightStatus = Literal["ok", "warning", "error", "skipped"]


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: PreflightStatus
    detail: str = ""


@dataclass(frozen=True)
class PreflightReport:
    profile: str
    model: str
    base_url: str
    tool_mode: str
    state_mode: str
    overall: PreflightStatus
    checks: list[PreflightCheck]


def _profile_expectations(settings: Settings) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    profile = settings.llm_profile
    if profile == "openai-native":
        if settings.llm_tool_mode != "openai_computer":
            checks.append(
                PreflightCheck(
                    name="tool_mode",
                    status="error",
                    detail="openai-native profile requires LLM_TOOL_MODE=openai_computer",
                )
            )
        if settings.llm_state_mode != "server":
            checks.append(
                PreflightCheck(
                    name="state_mode",
                    status="warning",
                    detail="openai-native profile generally requires LLM_STATE_MODE=server",
                )
            )
    elif profile == "ollama-stateless":
        if settings.llm_state_mode != "manual":
            checks.append(
                PreflightCheck(
                    name="state_mode",
                    status="warning",
                    detail="ollama-stateless profile expects LLM_STATE_MODE=manual",
                )
            )
        if settings.llm_tool_mode != "function_computer":
            checks.append(
                PreflightCheck(
                    name="tool_mode",
                    status="warning",
                    detail="ollama-stateless profile expects LLM_TOOL_MODE=function_computer",
                )
            )
    elif profile in {"lmstudio-responses", "vllm-responses"}:
        if settings.llm_tool_mode == "openai_computer":
            checks.append(
                PreflightCheck(
                    name="tool_mode",
                    status="error",
                    detail=f"{profile} does not support native computer tool; use function_computer",
                )
            )
    if not settings.llm_supports_tool_calls:
        checks.append(
            PreflightCheck(
                name="tool_calls",
                status="error",
                detail="LLM_SUPPORTS_TOOL_CALLS=false; computer agent cannot operate",
            )
        )
    if not settings.llm_supports_vision:
        checks.append(
            PreflightCheck(
                name="vision",
                status="warning",
                detail="LLM_SUPPORTS_VISION=false; agent will operate without screenshots",
            )
        )
    if not settings.llm_api_key and profile != "mock":
        checks.append(
            PreflightCheck(
                name="api_key",
                status="error",
                detail="LLM_API_KEY is empty",
            )
        )
    return checks


async def _probe_responses_endpoint(settings: Settings) -> PreflightCheck:
    if settings.llm_profile == "mock":
        return PreflightCheck(name="responses_reachable", status="skipped", detail="mock profile")
    if not settings.llm_api_key:
        return PreflightCheck(
            name="responses_reachable",
            status="skipped",
            detail="API key missing; skipping reachability probe",
        )
    target = settings.llm_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{target}/models",
                headers={"authorization": f"Bearer {settings.llm_api_key}"},
            )
        if response.status_code in (200, 401, 403):
            return PreflightCheck(
                name="responses_reachable",
                status="ok",
                detail=f"reachable ({response.status_code})",
            )
        return PreflightCheck(
            name="responses_reachable",
            status="warning",
            detail=f"unexpected status {response.status_code}",
        )
    except httpx.HTTPError as exc:
        return PreflightCheck(
            name="responses_reachable",
            status="warning",
            detail=f"could not reach {target}: {exc}",
        )


async def run_preflight(settings: Settings) -> PreflightReport:
    checks = _profile_expectations(settings)
    checks.append(await _probe_responses_endpoint(settings))
    overall: PreflightStatus = "ok"
    if any(check.status == "error" for check in checks):
        overall = "error"
    elif any(check.status == "warning" for check in checks):
        overall = "warning"
    return PreflightReport(
        profile=settings.llm_profile,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        tool_mode=settings.llm_tool_mode,
        state_mode=settings.llm_state_mode,
        overall=overall,
        checks=checks,
    )


def report_to_dict(report: PreflightReport) -> dict[str, Any]:
    return {
        "profile": report.profile,
        "model": report.model,
        "base_url": report.base_url,
        "tool_mode": report.tool_mode,
        "state_mode": report.state_mode,
        "overall": report.overall,
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail}
            for check in report.checks
        ],
    }
