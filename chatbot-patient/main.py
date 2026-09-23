"""Main entry point for the MedAI Patient Assistant (chatbot-patient)."""
import atexit
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, List, Optional, Tuple

from fastapi import FastAPI

from app.api.routes.agent import router as agent_router
from app.api.routes.whatsapp import router as whatsapp_router
from app.agents.prompt_loader import loader
from app.core.config import settings
from app.core.logging_setup import setup_logging
from app.infrastructure import tools

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_FILE = setup_logging(log_level=settings.log_level, log_dir=_LOG_DIR)
logger = logging.getLogger(__name__)

# Local `py main.py` convenience: spawn any [PATIENT] tool service that is DOWN.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _REPO_ROOT / "services"
_DATA_DIR = _REPO_ROOT / "data"
_DB_SERVICES = {"AppointmentSchedulerService", "MyRecordService"}
_CHILD_PROCS: List[Tuple[str, subprocess.Popen]] = []
_CHILD_LOGS: List[IO[str]] = []

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(agent_router)
app.include_router(whatsapp_router)


def _auto_start_enabled() -> bool:
    flag = os.environ.get("AUTO_START_TOOLS", "true").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _tools_host_is_local() -> bool:
    host = (settings.medai_tools_host or os.environ.get("MEDAI_TOOLS_HOST") or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _service_state(status: dict) -> str:
    if status.get("healthy"):
        return "healthy"
    if status.get("reachable"):
        return "reachable"
    return "DOWN"


def _start_service(name: str) -> Optional[subprocess.Popen]:
    spec = tools.SERVICES.get(name)
    cwd = _SERVICES_DIR / name
    script = cwd / "main.py"
    if spec is None or not script.exists():
        logger.error("Cannot start %s: %s is missing", name, script)
        return None

    env = os.environ.copy()
    # Parent .env has PORT=8030; children must not inherit that.
    env["PORT"] = str(spec.port)
    env["API_PORT"] = str(spec.port)
    env["API_RELOAD"] = "false"
    if name in _DB_SERVICES:
        env["MEDAI_DATA_DIR"] = str(_DATA_DIR)

    _LOG_DIR.mkdir(exist_ok=True)
    log_path = _LOG_DIR / f"{name}.log"
    log_fh = log_path.open("a", encoding="utf-8", buffering=1)
    _CHILD_LOGS.append(log_fh)

    kwargs = {}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(cwd),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    logger.info("Started %s (pid=%s, port=%s) — logs: %s", name, proc.pid, spec.port, log_path)
    return proc


def _wait_for_started(names: List[str], timeout_s: float = 30.0) -> None:
    pending = set(names)
    deadline = time.time() + timeout_s
    while pending and time.time() < deadline:
        health = tools.health()
        for name in list(pending):
            if _service_state(health.get(name) or {}) != "DOWN":
                logger.info("  %s is up", name)
                pending.discard(name)
        if pending:
            time.sleep(0.5)
    for name in pending:
        logger.error(
            "%s did not become reachable in time — see %s",
            name, _LOG_DIR / f"{name}.log",
        )


def ensure_patient_services() -> None:
    """Start any enabled patient tool service that is not already reachable."""
    if not _auto_start_enabled():
        logger.info("AUTO_START_TOOLS is disabled; not launching local tool services")
        return
    if not _tools_host_is_local():
        logger.info(
            "MEDAI_TOOLS_HOST=%s is not localhost; not launching local tool services",
            settings.medai_tools_host or "(unset)",
        )
        return

    down = [
        name for name, status in tools.health().items()
        if _service_state(status) == "DOWN" and name in tools.SERVICES
    ]
    if not down:
        return

    started: List[str] = []
    for name in down:
        logger.info("%s is DOWN — launching %s", name, _SERVICES_DIR / name)
        proc = _start_service(name)
        if proc is None:
            continue
        _CHILD_PROCS.append((name, proc))
        started.append(name)

    if started:
        _wait_for_started(started)


def stop_started_services() -> None:
    """Stop only the tool processes this process spawned."""
    for name, proc in _CHILD_PROCS:
        if proc.poll() is not None:
            continue
        logger.info("Stopping %s (pid=%s)", name, proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            logger.warning("Forcing stop for %s (pid=%s)", name, proc.pid)
            proc.kill()
    _CHILD_PROCS.clear()
    for fh in _CHILD_LOGS:
        try:
            fh.close()
        except Exception:
            pass
    _CHILD_LOGS.clear()


atexit.register(stop_started_services)


@app.get("/")
async def root():
    return {
        "message": "MedAI Patient Assistant is running!",
        "version": settings.api_version,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Liveness plus the two things that make this agent safe to serve: its prompts
    loaded, and its tool set resolved."""
    services = tools.health()
    operations = sorted(tools.active_operations())
    healthy = loader.loaded and bool(operations)
    return {
        "status": "healthy" if healthy else "degraded",
        "prompts_loaded": loader.loaded,
        "prompts_file": str(settings.prompts_path),
        "operations": operations,
        "services": services,
        "whatsapp_configured": settings.whatsapp_configured,
    }


@app.on_event("startup")
async def startup_event():
    setup_logging(log_level=settings.log_level, log_dir=_LOG_DIR)
    logger.info("Starting %s v%s on port %s",
                settings.api_title, settings.api_version, settings.api_port)
    logger.info("Log file (persistent): %s", _LOG_FILE)
    logger.info(
        "Database: %s %s@%s:%s/%s schema=%s password_set=%s",
        settings.db_type, settings.db_user, settings.db_host, settings.db_port,
        settings.db_name, settings.db_schema, bool(settings.db_password),
    )
    logger.info("Asklepios schema: %s", settings.schema_graph_path)
    if not loader.loaded:
        logger.error("Prompts NOT loaded from %s — the agent will not behave correctly",
                     settings.prompts_path)
    ops = tools.active_operations()
    logger.info("Patient tools active: %s", ", ".join(sorted(ops)) or "(none)")
    if settings.whatsapp_configured:
        logger.info("WhatsApp webhook ready at /webhook/whatsapp")
    else:
        logger.warning("WhatsApp is not fully configured (verify token / app secret / access token / phone id)")
    ensure_patient_services()
    for name, status in tools.health().items():
        logger.info("  %-30s %-34s %s",
                    name, status.get("url", ""), _service_state(status))


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down MedAI Patient Assistant")
    stop_started_services()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.api_port))
    setup_logging(log_level=settings.log_level, log_dir=_LOG_DIR)
    logger.info("Log file (persistent): %s", _LOG_FILE)
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
        log_config=None,
    )