"""Main FastAPI application"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api.middleware import RequestIDMiddleware
from app.api.routes import summaries, presentations
from app.domain.normalization import ConceptNormalizer, load_mappings_from_yaml
from app.infrastructure.openai_client import OpenAIClient
from app.infrastructure.pptx_generator import PPTXGenerator
from app.application.summarize_use_case import SummarizeUseCase
from app.application.presentation_use_case import PresentationUseCase

# Load environment variables from .env file
load_dotenv()


# Initialize FastAPI app
app = FastAPI(
    title="ICU Summarizer API",
    description="REST API for generating ICU daily summaries and handoff presentations",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID middleware
app.add_middleware(RequestIDMiddleware)

# Load configuration
config_dir = Path(__file__).parent.parent / "config"
mappings_path = config_dir / "mappings.yml"

# Initialize infrastructure
normalizer = ConceptNormalizer(load_mappings_from_yaml(mappings_path))

# Initialize OpenAI client (will fail at runtime if API key not set)
try:
    openai_client = OpenAIClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_name=os.getenv("MODEL_NAME", "gpt-4o")
    )
except Exception:
    # Allow app to start without API key for testing (will fail on actual API calls)
    openai_client = None

pptx_generator = PPTXGenerator()

# Initialize use cases (will fail at runtime if openai_client is None)
if openai_client:
    summarize_use_case = SummarizeUseCase(normalizer, openai_client)
    presentation_use_case = PresentationUseCase(normalizer, openai_client, pptx_generator)
else:
    summarize_use_case = None
    presentation_use_case = None


# Set the use case instances in route modules
# This approach works reliably with uvicorn reload
summaries._summarize_use_case_instance = summarize_use_case
presentations._presentation_use_case_instance = presentation_use_case

# Include routers
app.include_router(summaries.router)
app.include_router(presentations.router)

# Use startup event to ensure dependency injection is always applied on reload
@app.on_event("startup")
async def startup_event():
    """Ensure dependency injection is applied on startup/reload"""
    summaries._summarize_use_case_instance = summarize_use_case
    presentations._presentation_use_case_instance = presentation_use_case


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
