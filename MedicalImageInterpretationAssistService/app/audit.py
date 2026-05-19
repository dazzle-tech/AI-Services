from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_audit_logger = logging.getLogger("miias.audit")
_configured = False


def _configure_audit_logger() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False

    # Always log to stdout so container collectors pick it up.
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(stdout_handler)

    # Optionally log to a rotating file if the directory is writable.
    log_dir = Path(os.environ.get("AUDIT_LOG_DIR", "/var/log/miias"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "audit.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        _audit_logger.addHandler(file_handler)
    except OSError:
        # Directory not writable (e.g. in tests or read-only containers).
        # Stdout logging is sufficient.
        pass


def log_interpretation(
    *,
    study_instance_uid: str | None,
    exam_type: str,
    status: str,
    finding_codes: list[str],
    critical_alert: bool,
    model_name: str,
    modality_handled: str,
    clinical_indication: str | None,
    warnings: list[str],
) -> None:
    """Write one structured JSON audit line per interpretation request."""
    _configure_audit_logger()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "study_instance_uid": study_instance_uid,
        "exam_type": exam_type,
        "status": status,
        "finding_codes": finding_codes,
        "critical_alert": critical_alert,
        "model_name": model_name,
        "modality_handled": modality_handled,
        "clinical_indication": clinical_indication,
        "warnings": warnings,
    }
    _audit_logger.info(json.dumps(record))
