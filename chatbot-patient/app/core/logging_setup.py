"""Logging setup: console + persistent file so WhatsApp turns stay visible."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_CONFIGURED = False


def setup_logging(*, log_level: str = "INFO", log_dir: Path) -> Path:
    """Attach stdout and an append-only file handler to the root logger.

    Uvicorn reconfigures logging on startup; we call this from ``main.py`` before
    ``uvicorn.run`` and again on FastAPI startup so app + access logs land in both
    places and are never lost when the IDE terminal scroll buffer clears.
    """
    global _CONFIGURED
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "patient-agent.log"

    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    # Replace handlers so reload / double-import does not duplicate lines.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        uv_log = logging.getLogger(name)
        uv_log.handlers.clear()
        uv_log.propagate = True
        uv_log.setLevel(level)

    _CONFIGURED = True
    logging.getLogger(__name__).info("Logging to console and %s", log_file)
    return log_file
