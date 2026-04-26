from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "display": {
            "width": settings.display_width,
            "height": settings.display_height,
            "depth": settings.display_depth,
        },
    }
