from __future__ import annotations

from typing import Dict

from fastapi import Depends, FastAPI

from .config import Settings, get_settings
from .ct import ct_router
from .interpretation import interpretation_router

app = FastAPI(title="Medical Image Interpretation Assist Service", version="0.1.0")

app.include_router(
    interpretation_router,
    prefix="/api/v1/radiology/xray-interpretation",
    tags=["X-ray Interpretation Assist"],
)

app.include_router(
    ct_router,
    prefix="/api/v1/radiology/ct-interpretation",
    tags=["CT Interpretation Assist"],
)


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> Dict[str, str]:
    return {"status": "ok", "service": settings.service_name}
