"""Main entry point for SQL Generator Service."""
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import sql_generator
from app.infrastructure.config.schema_graph_repo import SchemaGraphRepository

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | sql_generator | %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SQL Generator Service",
    version="4.1.0",
    description="SQL generation microservice for MedAI Assistant"
)

# Include router
app.include_router(sql_generator.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "SQL Generator Service",
        "status": "healthy",
    }


@app.get("/")
def root():
    """Root endpoint."""
    schema_repo = SchemaGraphRepository()
    schema_graph = schema_repo.load_or_create()
    table_count = len(schema_graph)
    col_count = sum(len(t["columns"]) for t in schema_graph.values())
    return {
        "ok": True,
        "service": "SQL Generator (Schema-Graph Intelligent)",
        "model": settings.sql_gen_model,
        "db_path": settings.hospital_db_path,
        "tables": table_count,
        "columns": col_count,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting Intelligent SQL Generator on port 8001")
    port = int(os.environ.get("PORT", settings.sql_generator_port))
    
    # Get the chatbot directory for reload watching
    chatbot_dir = Path(__file__).parent.parent
    
    uvicorn.run(
        "runners.main_sql_generator:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        reload_dirs=[str(chatbot_dir / "app"), str(chatbot_dir / "runners")] if settings.api_reload else None,
        log_level="info"
    )



