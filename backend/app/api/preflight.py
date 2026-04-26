from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.llm.preflight import report_to_dict, run_preflight

router = APIRouter(tags=["preflight"])


@router.get("/preflight")
async def preflight(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    report = await run_preflight(settings)
    return report_to_dict(report)
