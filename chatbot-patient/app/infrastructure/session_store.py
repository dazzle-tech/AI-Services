"""Session store for the patient agent.

The implementation is ``medai_core.session.store``, shared with the clinician bot. This
module binds it to the patient bot's settings, key prefix and default session shape.

Holds per-session conversation history, the authenticated patient identity, any pending
confirmation, and the slots/appointments last shown. Never holds clinical data — that is
read from the tools on each turn, per the project's Redis-as-staging-cache decision.

The prefix MUST stay distinct from the clinician bot's ("medai:session:"). Both bots
share one Redis instance, and the prefix is what keeps a patient's conversation out of
the clinician agent's session space.
"""
import logging
from typing import Any, Dict, Optional

from medai_core.session.store import REDIS_AVAILABLE, SessionStore as _CoreSessionStore

from app.core.config import settings

logger = logging.getLogger(__name__)

__all__ = ["SessionStore", "get_session_store", "REDIS_AVAILABLE"]

_KEY_PREFIX = "medai:patient-session:"


def _default_session() -> Dict[str, Any]:
    return {
        "history": [],
        "patient_id": None,
        "patient_mrn": None,
        "patient_name": None,
        "pending": None,
        "last_slots": [],
        "last_appointments": [],
    }


class SessionStore(_CoreSessionStore):
    """Patient session store: shared implementation, patient configuration."""

    def __init__(self):
        super().__init__(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            ttl_seconds=settings.session_ttl_seconds,
            prefix=_KEY_PREFIX,
            default_factory=_default_session,
        )

    def clear(self, session_id: str) -> None:
        """Alias for delete() — reads better at the sign-out call site."""
        self.delete(session_id)


_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
