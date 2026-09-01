"""Structured logging without PHI."""

import logging
import re

from app.core.config import settings

PHI_PATTERNS = (
    re.compile(r'"text"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"subjective"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"objective"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"assessment"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"plan"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"description"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"reasoning"\s*:\s*"[^"]*"', re.IGNORECASE),
)


def scrub_phi(message: str) -> str:
    scrubbed = message
    for pattern in PHI_PATTERNS:
        scrubbed = pattern.sub(lambda m: m.group(0).split(":")[0] + ': "[REDACTED]"', scrubbed)
    return scrubbed


class PHIFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_phi(record.msg)
        if record.args:
            record.args = tuple(
                scrub_phi(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True


class ContextFilter(logging.Filter):
    """Ensure format placeholders exist without blocking logging `extra` fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("view_id", "-")
        record.__dict__.setdefault("event_type", "-")
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s view=%(view_id)s event=%(event_type)s — %(message)s",
        force=True,
    )
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(PHIFilter())
        handler.addFilter(ContextFilter())


def get_logger(name: str) -> logging.Logger:
    """Return a standard logger; pass view_id/event_type via extra=."""
    return logging.getLogger(name)
