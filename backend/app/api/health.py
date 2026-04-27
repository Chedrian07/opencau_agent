from fastapi import APIRouter, Request

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = get_settings()
    session_manager = getattr(request.app.state, "session_manager", None)
    return {
        "status": "ok",
        "display": {
            "width": settings.display_width,
            "height": settings.display_height,
            "depth": settings.display_depth,
        },
        "llm": {
            "profile": settings.llm_profile,
            "model": settings.llm_model,
            "tool_mode": settings.llm_tool_mode,
            "state_mode": settings.llm_state_mode,
        },
        "agent": {
            "max_steps": settings.max_agent_steps,
            "timeout_sec": settings.agent_timeout_sec,
        },
        "storage": {
            "session_backend": getattr(session_manager, "backend_name", "uninitialized"),
            "sqlite_path": settings.sqlite_path,
            "screenshot_retention_hours": settings.screenshot_retention_hours,
        },
    }
