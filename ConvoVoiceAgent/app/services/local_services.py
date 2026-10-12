"""Start the bundled ConvoScribe and SystemDisplayPlugin processes when they are down."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_START_TIMEOUT_SECONDS = 60.0
_POLL_SECONDS = 0.5


def ensure_downstream() -> list[subprocess.Popen]:
    """Return only the processes this call started. Already-running services are left alone."""
    started: list[subprocess.Popen] = []
    started.extend(
        _ensure(
            "ConvoScribe",
            f"{settings.convoscribe_base_url.rstrip('/')}/api/v1/health",
            _AGENT_ROOT / "services" / "ConvoScribe",
            _AGENT_ROOT / "services" / "ConvoScribe" / ".env",
        )
    )
    started.extend(
        _ensure(
            "SystemDisplayPlugin",
            f"{settings.system_display_base_url.rstrip('/')}/api/v1/health",
            _AGENT_ROOT / "services" / "SystemDisplayPlugin",
            _AGENT_ROOT / "services" / "SystemDisplayPlugin" / ".env",
        )
    )
    return started


def stop_started(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is not None:
            continue
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _ensure(name: str, health_url: str, workdir: Path, env_file: Path) -> list[subprocess.Popen]:
    if _healthy(health_url):
        logger.info("%s is already running", name, extra={"event_type": "downstream_start"})
        return []
    if not (workdir / "main.py").is_file():
        logger.warning(
            "%s code is missing at %s",
            name,
            workdir,
            extra={"event_type": "downstream_start"},
        )
        return []

    logger.info("Starting %s", name, extra={"event_type": "downstream_start"})
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(workdir),
        env=_child_env(env_file, health_url),
    )
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            logger.warning(
                "%s exited before it became healthy (code %s)",
                name,
                process.returncode,
                extra={"event_type": "downstream_start"},
            )
            return []
        if _healthy(health_url):
            logger.info("%s is up", name, extra={"event_type": "downstream_start"})
            return [process]
        time.sleep(_POLL_SECONDS)

    logger.warning("%s did not become healthy", name, extra={"event_type": "downstream_start"})
    return [process]


def _healthy(url: str) -> bool:
    try:
        response = httpx.get(url, timeout=2.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _child_env(env_file: Path, service_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(_parse_env_file(env_file))
    port = urlparse(service_url).port
    if port:
        # The agent process may already have API_PORT/PORT set for itself.
        # The child must listen on the URL this agent will call.
        env["API_PORT"] = str(port)
        env["PORT"] = str(port)
    env["API_HOST"] = "0.0.0.0"
    return env


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values
