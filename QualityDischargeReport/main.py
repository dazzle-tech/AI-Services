"""Application entrypoint."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from fastapi import FastAPI
from src.api.discharge_qa import router as discharge_qa_router

app = FastAPI(
    title="Discharge QA Service",
    description="Clinical discharge report quality assurance engine",
    version="1.0.0"
)

# Register routers
app.include_router(discharge_qa_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Discharge QA Service",
        "version": "1.0.0",
        "endpoints": {
            "qa": "/discharge/qa/direct"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "8011"))
    uvicorn.run(app, host="0.0.0.0", port=port)

