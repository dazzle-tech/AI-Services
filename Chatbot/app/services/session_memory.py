"""
Session memory management service.

This service now uses Redis for session storage instead of in-memory dictionaries
and JSON files. This enables:
- Shared session state across multiple orchestrator instances
- Automatic expiration of old sessions (24h TTL)
- Persistent session memory that survives service restarts

Session memory stores temporary context for:
- Pronoun resolution ("he", "this patient")
- Follow-up cohort queries
- Avoiding repeated patient identification
- Intent continuity

Note: This is separate from audit logs (stored in audit.db), which contain
permanent records of all interactions.
"""
import logging
from typing import Dict, Any, Optional
from app.infrastructure.session_store import SessionStore, get_session_store

logger = logging.getLogger(__name__)


class SessionMemoryService:
    """
    Service for managing persistent session memory using Redis.
    
    Replaces the previous in-memory + JSON file approach with Redis-backed storage.
    All session operations are now handled by the Redis SessionStore.
    """
    
    def __init__(self, session_store: Optional[SessionStore] = None):
        """
        Initialize session memory service.
        
        Args:
            session_store: Optional SessionStore instance (defaults to global instance)
        """
        self.session_store = session_store or get_session_store()
        logger.info("🧠 SessionMemoryService initialized with Redis backend")
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Retrieve or initialize a chat session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session dictionary with default structure if new session
        """
        return self.session_store.get(session_id)
    
    def save_session(self, session_id: str, session: Optional[Dict[str, Any]] = None):
        """
        Save session to Redis.
        
        Args:
            session_id: Session identifier
            session: Optional session dict to save. If not provided, retrieves
                     current session from Redis and saves it (updates TTL).
        """
        if session is not None:
            # Save the provided session dict
            self.session_store.set(session_id, session)
        else:
            # Get current session and save it (this will update TTL)
            current = self.session_store.get(session_id)
            self.session_store.set(session_id, current)
    
    def update_session(self, session_id: str, patch: Dict[str, Any]):
        """
        Partially update session data.
        
        Args:
            session_id: Session identifier
            patch: Dictionary of fields to update
        """
        self.session_store.update(session_id, patch)
    
    def clear_all_sessions(self):
        """
        Clear all sessions from Redis.
        
        This removes all session keys matching pattern medai:session:*
        Does NOT affect audit logs (audit.db).
        """
        deleted = self.session_store.clear_all()
        logger.info(f"🧹 Cleared {deleted} session(s) from Redis")
    
    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all sessions (for debugging/admin purposes).
        
        Returns:
            Dictionary mapping session_id to session data
        """
        return self.session_store.get_all_sessions()


# Global instance
_session_memory_service = SessionMemoryService()


def get_session(session_id: str) -> Dict[str, Any]:
    """Legacy function for backward compatibility."""
    return _session_memory_service.get_session(session_id)


def save_sessions(session_id: Optional[str] = None):
    """Legacy function for backward compatibility."""
    if session_id:
        _session_memory_service.save_session(session_id)


def clear_all_sessions():
    """Legacy function for backward compatibility."""
    _session_memory_service.clear_all_sessions()



