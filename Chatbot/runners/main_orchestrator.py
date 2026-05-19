"""Main entry point for MedAI Orchestrator Service."""
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import app
chatbot_dir = Path(__file__).parent.parent
sys.path.insert(0, str(chatbot_dir))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.api.routes import chat, admin, patient_details, interaction_details

# Configure logging - use both console and file
log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
log_file = chatbot_dir / "orchestrator.log"

# Start each run with a fresh log file (truncate/remove old log).
try:
    if log_file.exists():
        log_file.unlink()
except Exception:
    # If the file is locked (e.g., running service), fall back to truncation.
    try:
        with open(log_file, "w", encoding="utf-8"):
            pass
    except Exception:
        pass

# Clear existing handlers
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(log_format))

# File handler
file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(log_format))

# Configure root logger
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)
logger.info(f"📝 Logging to console and file: {log_file}")
print(f"[STARTUP] Logging to file: {log_file}", flush=True)

# Create FastAPI app
app = FastAPI(
    title="MedAI Assistant – Chat Orchestrator",
    version="2.0.0",
    description="Multi-service hospital assistant orchestrator"
)

def _load_allowed_origins() -> list[str]:
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ]
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


allowed_origins = _load_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS enabled for origins: %s", allowed_origins)
# Add request logging middleware - MUST be first to catch all requests
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log to file directly as backup
        log_file = chatbot_dir / "orchestrator.log"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[MIDDLEWARE] {request.method} {request.url.path}\n")
            f.write(f"[MIDDLEWARE] Query params: {dict(request.query_params)}\n")
            f.flush()
        
        msg = f"\n{'='*60}\n[MIDDLEWARE] {request.method} {request.url.path}\n"
        print(msg, flush=True, file=sys.stderr)
        print(msg, flush=True, file=sys.stdout)
        logger.info(f"🌐 {request.method} {request.url.path}")
        root_logger = logging.getLogger()
        root_logger.info(f"🌐 MIDDLEWARE: {request.method} {request.url.path}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        response = await call_next(request)
        
        # Log response to file directly
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[MIDDLEWARE] Response: {response.status_code}\n")
            f.write(f"{'='*60}\n")
            f.flush()
        
        msg2 = f"[MIDDLEWARE] Response status: {response.status_code}\n{'='*60}\n"
        print(msg2, flush=True, file=sys.stderr)
        print(msg2, flush=True, file=sys.stdout)
        logger.info(f"✅ {request.method} {request.url.path} -> {response.status_code}")
        root_logger.info(f"✅ MIDDLEWARE: {request.method} {request.url.path} -> {response.status_code}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        return response

# Add middleware first
app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(patient_details.router)
app.include_router(interaction_details.router)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "ok": True,
        "service": "MedAI Orchestrator",
        "audit_db": settings.audit_db_path,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.orchestrator_port))
    logger.info("🚀 Starting Orchestrator on port %s", port)
    
    uvicorn.run(
        "runners.main_orchestrator:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        reload_dirs=[str(chatbot_dir / "app"), str(chatbot_dir / "runners")] if settings.api_reload else None,
        log_level="info",
        use_colors=True,
        access_log=True,  # Enable access logs
        timeout_keep_alive=120,  # Keep connections alive for 120 seconds (for long CrewAI requests)
        timeout_graceful_shutdown=30,  # Graceful shutdown timeout
    )



