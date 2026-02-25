"""Main entry point for Validator Service."""
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import validator

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | validator | %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SQL Validator + Executor Service",
    version="2.3",
    description="SQL validation and execution microservice"
)

# Include router
app.include_router(validator.router)


if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting Validator Service on port 8002")
    port = int(os.environ.get("PORT", settings.validator_port))
    
    # Get the chatbot directory for reload watching
    chatbot_dir = Path(__file__).parent.parent
    
    uvicorn.run(
        "runners.main_validator:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        reload_dirs=[str(chatbot_dir / "app"), str(chatbot_dir / "runners")] if settings.api_reload else None,
        log_level="info"
    )



