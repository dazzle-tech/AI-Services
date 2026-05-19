"""
Redis-based session store for MedAI Assistant.

This module provides a Redis-backed session memory store that replaces the previous
in-memory dictionary + JSON file approach. Sessions are stored in Redis with TTL-based
expiration, enabling:
- Shared session state across multiple orchestrator instances
- Automatic expiration of old sessions
- Persistent session memory that survives service restarts

Session Memory vs Audit Logs:
- Session Memory: Temporary context for pronoun resolution, follow-up queries, and
  intent continuity. Stored in Redis with 24h TTL. Contains: last_patient, last_patient_id,
  last_patient_ids (cohort), last_intent, history.
- Audit Logs: Permanent record of all interactions stored in SQLite (audit.db).
  Contains: full interaction history, SQL queries, service calls, timestamps.

Session data structure:
{
  "last_patient": "John Doe",
  "last_patient_id": 1001,
  "last_patient_ids": [1001, 1002],
  "last_intent": "data",
  "history": []
}
"""
import json
import logging
import threading
import time
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import redis, but handle gracefully if not available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️ Redis library not installed. Install with: pip install redis")


class SessionStore:
    """
    Redis-based session store abstraction.
    
    Provides a clean interface for session operations with automatic TTL management.
    All methods are safe if Redis is unavailable - they will log warnings and return
    default values without crashing the application.
    """

    # In-process fallback store for when Redis is unavailable.
    # NOTE: This does not share session state across multiple workers/containers.
    _fallback_lock = threading.Lock()
    _fallback_sessions: Dict[str, Dict[str, Any]] = {}
    _fallback_expiry: Dict[str, float] = {}
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ):
        """
        Initialize Redis session store.
        
        Args:
            host: Redis host (defaults to REDIS_HOST env var or localhost)
            port: Redis port (defaults to REDIS_PORT env var or 6379)
            db: Redis database number (defaults to REDIS_DB env var or 0)
            ttl_seconds: Session TTL in seconds (defaults to SESSION_TTL_SECONDS env var or 86400)
        """
        self.host = host or settings.redis_host
        self.port = port or settings.redis_port
        self.db = db or settings.redis_db
        self.ttl_seconds = ttl_seconds or settings.session_ttl_seconds
        self._client: Optional[redis.Redis] = None
        self._connected = False
        self._use_fallback = True
        
        if not REDIS_AVAILABLE:
            logger.warning("⚠️ Redis library not available. Session store will use fallback mode.")
            return
        
        try:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,  # Increased from 2 to 5 seconds
                socket_timeout=5,  # Increased from 2 to 5 seconds
                socket_keepalive=True,
                health_check_interval=30,
            )
            # Test connection with retry
            self._client.ping()
            self._connected = True
            self._use_fallback = False
            logger.info(f"✅ Connected to Redis at {self.host}:{self.port}/{self.db}")
        except redis.ConnectionError as e:
            logger.warning(f"⚠️ Failed to connect to Redis: {e}. Session store will use fallback mode.")
            logger.info(f"💡 Make sure Redis is running. Start with: docker start redis-medai")
            self._connected = False
            self._client = None
        except Exception as e:
            logger.warning(f"⚠️ Failed to connect to Redis: {e}. Session store will use fallback mode.")
            self._connected = False
            self._client = None
    
    def _get_key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"medai:session:{session_id}"
    
    def _get_default_session(self) -> Dict[str, Any]:
        """Return default empty session structure."""
        return {
            "last_patient": None,
            "last_patient_id": None,
            "last_patient_mrn": None,
            "last_patient_ids": None,  # cohort memory
            "last_intent": None,
            "last_data_question": None,
            "history": [],
        }
    
    def get(self, session_id: str) -> Dict[str, Any]:
        """
        Retrieve session data from Redis.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session dictionary. Returns default empty session if not found or Redis unavailable.
        """
        if not self._connected or not self._client:
            if self._use_fallback:
                now = time.time()
                with self._fallback_lock:
                    exp = self._fallback_expiry.get(session_id)
                    if exp is not None and exp <= now:
                        self._fallback_sessions.pop(session_id, None)
                        self._fallback_expiry.pop(session_id, None)
                        return self._get_default_session()
                    existing = self._fallback_sessions.get(session_id)
                    if existing is None:
                        return self._get_default_session()
                    return json.loads(json.dumps(existing, ensure_ascii=False))

            logger.debug(f"Redis unavailable, returning default session for {session_id}")
            return self._get_default_session()
        
        try:
            key = self._get_key(session_id)
            data = self._client.get(key)
            
            if data is None:
                # Session doesn't exist, return default
                return self._get_default_session()
            
            # Parse JSON and reset TTL on read
            session = json.loads(data)
            self._client.expire(key, self.ttl_seconds)
            logger.debug(f"Retrieved session {session_id} from Redis")
            return session
        except Exception as e:
            logger.warning(f"⚠️ Failed to get session {session_id} from Redis: {e}")
            return self._get_default_session()
    
    def set(self, session_id: str, data: Dict[str, Any]):
        """
        Store complete session data in Redis with TTL.
        
        Args:
            session_id: Session identifier
            data: Complete session dictionary to store
        """
        if not self._connected or not self._client:
            if self._use_fallback:
                with self._fallback_lock:
                    self._fallback_sessions[session_id] = json.loads(json.dumps(data, ensure_ascii=False))
                    self._fallback_expiry[session_id] = time.time() + float(self.ttl_seconds or 0)
                return

            logger.debug(f"Redis unavailable, skipping set for {session_id}")
            return
        
        try:
            key = self._get_key(session_id)
            json_data = json.dumps(data, ensure_ascii=False)
            self._client.setex(key, self.ttl_seconds, json_data)
            logger.debug(f"Stored session {session_id} in Redis with TTL {self.ttl_seconds}s")
        except Exception as e:
            logger.warning(f"⚠️ Failed to set session {session_id} in Redis: {e}")
    
    def update(self, session_id: str, patch: Dict[str, Any]):
        """
        Partially update session data in Redis.
        
        Args:
            session_id: Session identifier
            patch: Dictionary of fields to update (merged with existing session)
        """
        if not self._connected or not self._client:
            if self._use_fallback:
                current = self.get(session_id)
                current.update(patch)
                self.set(session_id, current)
                return

            logger.debug(f"Redis unavailable, skipping update for {session_id}")
            return
        
        try:
            # Get existing session
            current = self.get(session_id)
            # Merge patch
            current.update(patch)
            # Save back
            self.set(session_id, current)
            logger.debug(f"Updated session {session_id} in Redis")
        except Exception as e:
            logger.warning(f"⚠️ Failed to update session {session_id} in Redis: {e}")
    
    def delete(self, session_id: str):
        """
        Delete a session from Redis.
        
        Args:
            session_id: Session identifier
        """
        if not self._connected or not self._client:
            if self._use_fallback:
                with self._fallback_lock:
                    self._fallback_sessions.pop(session_id, None)
                    self._fallback_expiry.pop(session_id, None)
                return

            logger.debug(f"Redis unavailable, skipping delete for {session_id}")
            return
        
        try:
            key = self._get_key(session_id)
            self._client.delete(key)
            logger.debug(f"Deleted session {session_id} from Redis")
        except Exception as e:
            logger.warning(f"⚠️ Failed to delete session {session_id} from Redis: {e}")
    
    def clear_all(self) -> int:
        """
        Clear all session keys matching pattern medai:session:*
        
        Returns:
            Number of keys deleted
        """
        if not self._connected or not self._client:
            if self._use_fallback:
                with self._fallback_lock:
                    deleted = len(self._fallback_sessions)
                    self._fallback_sessions.clear()
                    self._fallback_expiry.clear()
                    return deleted

            logger.warning("Redis unavailable, cannot clear sessions")
            return 0
        
        try:
            pattern = "medai:session:*"
            keys = list(self._client.scan_iter(match=pattern))
            if keys:
                deleted = self._client.delete(*keys)
                logger.info(f"🧹 Cleared {deleted} session(s) from Redis")
                return deleted
            else:
                logger.info("🧹 No sessions to clear")
                return 0
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear sessions from Redis: {e}")
            return 0
    
    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all sessions (for debugging/admin purposes).
        
        Returns:
            Dictionary mapping session_id to session data
        """
        if not self._connected or not self._client:
            if self._use_fallback:
                now = time.time()
                with self._fallback_lock:
                    expired = [sid for sid, exp in self._fallback_expiry.items() if exp <= now]
                    for sid in expired:
                        self._fallback_sessions.pop(sid, None)
                        self._fallback_expiry.pop(sid, None)
                    return json.loads(json.dumps(self._fallback_sessions, ensure_ascii=False))

            logger.debug("Redis unavailable, returning empty sessions dict")
            return {}
        
        try:
            pattern = "medai:session:*"
            sessions = {}
            for key in self._client.scan_iter(match=pattern):
                try:
                    data = self._client.get(key)
                    if data:
                        session_id = key.replace("medai:session:", "")
                        sessions[session_id] = json.loads(data)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse session from key {key}: {e}")
            return sessions
        except Exception as e:
            logger.warning(f"⚠️ Failed to get all sessions from Redis: {e}")
            return {}


# Global instance
_session_store = SessionStore()


def get_session_store() -> SessionStore:
    """Get the global session store instance."""
    return _session_store
