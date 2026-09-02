"""NurseHandOver API — FastAPI entry point.

A stateless AI service: it takes patient chart data and returns structured SBAR
handoff summaries. Shift state and confirmed handoffs are owned by the agent
(hospital.db), not by this service.

Run locally:
    uvicorn main:app --reload --port 8028
"""
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes.summary import router as summary_router

app = FastAPI(
    title="NurseHandOver",
    description=(
        "AI-powered nurse shift handoff documentation service. "
        "Generates structured SBAR summaries from patient chart data."
    ),
    version="1.0.0",
)

# Calls arrive from the dashboard's nginx proxy / the agent on the compose network.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(summary_router, prefix="/summary", tags=["Summary"])


@app.get("/health", tags=["System"])
def health_check():
    """Liveness probe — used by compose health-gating and the agent's tool registry."""
    return {
        "status": "ok",
        "service": "NurseHandOver",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": settings.openai_model,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.port)
