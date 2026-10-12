"""Logging that keeps dictated clinical text out of log lines."""

import logging
import re

from app.core.config import settings

PHI_PATTERNS = (
    re.compile(r'"(?:summary|transcript|follow_up)"\s*:\s*"[^"]*"', re.IGNORECASE),
)


def scrub_phi(message: str) -> str:
    scrubbed = message
    for pattern in PHI_PATTERNS:
        scrubbed = pattern.sub(lambda match: match.group(0).split(":")[0] + ': "[REDACTED]"', scrubbed)
    return scrubbed


class PHIFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_phi(record.msg)
        if record.args:
            record.args = tuple(scrub_phi(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        force=True,
    )
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(PHIFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
