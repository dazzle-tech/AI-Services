"""Structured logging without PHI."""

import logging
import re

from app.core.config import settings

PHI_PATTERNS = (
    re.compile(r'"text"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"transcribed_text"\s*:\s*"[^"]*"', re.IGNORECASE),
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
    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("case_id", "-")
        record.__dict__.setdefault("window_id", "-")
        record.__dict__.setdefault("event_type", "-")
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s case=%(case_id)s window=%(window_id)s event=%(event_type)s — %(message)s",
        force=True,
    )
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(PHIFilter())
        handler.addFilter(ContextFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
