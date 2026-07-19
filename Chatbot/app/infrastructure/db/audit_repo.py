"""Audit database repository."""
import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuditRepository:
    """Repository for audit/history database operations."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.audit_db_path
        self._init_db()
    
    def _connect(self) -> sqlite3.Connection:
        """Create database connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn
    
    def _init_db(self):
        """Initialize audit database tables."""
        conn = self._connect()
        cur = conn.cursor()
        
        # Interactions table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              user_id TEXT NOT NULL,
              session_id TEXT NOT NULL,
              role TEXT,
              channel TEXT DEFAULT 'web',
              intent TEXT,
              approved INTEGER DEFAULT 0,
              raw_message TEXT,
              final_message TEXT,
              reply_text TEXT,
              sql_query TEXT,
              row_count INTEGER,
              ok INTEGER DEFAULT 1,
              error TEXT
            );
        """)
        # Migrate existing DBs: add channel column if missing
        try:
            cur.execute("SELECT channel FROM interactions LIMIT 1")
        except sqlite3.OperationalError:
            cur.execute("ALTER TABLE interactions ADD COLUMN channel TEXT DEFAULT 'web';")
        
        # Tool execution audit log (Phase 4)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tool_executions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              interaction_id INTEGER,
              tool_name TEXT NOT NULL,
              user_id TEXT NOT NULL,
              role TEXT,
              is_write_action INTEGER DEFAULT 0,
              arguments_json TEXT,
              result_json TEXT,
              error TEXT,
              confirmation_token_id TEXT,
              ok INTEGER DEFAULT 1,
              FOREIGN KEY(interaction_id) REFERENCES interactions(id)
            );
        """)
        
        # WhatsApp message audit log (Phase 3)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              direction TEXT NOT NULL,
              phone_number TEXT NOT NULL,
              user_id TEXT,
              message_text TEXT,
              status TEXT,
              error TEXT
            );
        """)
        
        # Service calls table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS service_calls (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              interaction_id INTEGER NOT NULL,
              ts_utc TEXT NOT NULL,
              service TEXT NOT NULL,
              url TEXT,
              ok INTEGER DEFAULT 1,
              status_code INTEGER,
              latency_ms INTEGER,
              request_json TEXT,
              response_json TEXT,
              error TEXT,
              FOREIGN KEY(interaction_id) REFERENCES interactions(id)
            );
        """)
        
        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_interactions_user_ts ON interactions(user_id, ts_utc);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_interactions_session_ts ON interactions(session_id, ts_utc);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_service_calls_interaction ON service_calls(interaction_id);")
        
        # Full-text search (optional)
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts
                USING fts5(raw_message, final_message, reply_text, sql_query, content='interactions', content_rowid='id');
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
                  INSERT INTO interactions_fts(rowid, raw_message, final_message, reply_text, sql_query)
                  VALUES (new.id, new.raw_message, new.final_message, new.reply_text, new.sql_query);
                END;
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS interactions_ad AFTER DELETE ON interactions BEGIN
                  INSERT INTO interactions_fts(interactions_fts, rowid, raw_message, final_message, reply_text, sql_query)
                  VALUES ('delete', old.id, old.raw_message, old.final_message, old.reply_text, old.sql_query);
                END;
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS interactions_au AFTER UPDATE ON interactions BEGIN
                  INSERT INTO interactions_fts(interactions_fts, rowid, raw_message, final_message, reply_text, sql_query)
                  VALUES ('delete', old.id, old.raw_message, old.final_message, old.reply_text, old.sql_query);
                  INSERT INTO interactions_fts(rowid, raw_message, final_message, reply_text, sql_query)
                  VALUES (new.id, new.raw_message, new.final_message, new.reply_text, new.sql_query);
                END;
            """)
        except Exception as e:
            logger.warning(f"⚠️ FTS not available (ok): {e}")
        
        conn.commit()
        conn.close()
        logger.info(f"🧾 Audit DB ready: {self.db_path}")
    
    def _utc_now(self) -> str:
        """Get current UTC time as ISO string."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    def _redact(self, obj: Any) -> Any:
        """Redact sensitive fields."""
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                lk = str(k).lower()
                if "email" in lk:
                    out[k] = "[REDACTED_EMAIL]"
                elif "phone" in lk:
                    out[k] = "[REDACTED_PHONE]"
                elif "address" in lk:
                    out[k] = "[REDACTED_ADDRESS]"
                elif lk in ("patientid", "patients_id", "last_patient_id", "last_patient_ids") or "patient_id" in lk:
                    out[k] = "[REDACTED_PATIENT_ID]"
                else:
                    out[k] = self._redact(v)
            return out
        if isinstance(obj, list):
            return [self._redact(x) for x in obj]
        return obj
    
    def insert_interaction(
        self,
        user_id: str,
        session_id: str,
        role: Optional[str],
        intent: Optional[str],
        approved: bool,
        raw_message: str,
        final_message: str,
        channel: str = "web",
    ) -> int:
        """Insert a new interaction record."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO interactions(ts_utc, user_id, session_id, role, channel, intent, approved, raw_message, final_message, ok)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            self._utc_now(),
            user_id,
            session_id,
            role,
            channel,
            intent,
            1 if approved else 0,
            raw_message,
            final_message,
        ))
        interaction_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        return interaction_id
    
    def update_interaction(
        self,
        interaction_id: int,
        *,
        reply_text: Optional[str] = None,
        sql_query: Optional[str] = None,
        row_count: Optional[int] = None,
        ok: Optional[bool] = None,
        error: Optional[str] = None,
        intent: Optional[str] = None,
    ):
        """Update an existing interaction record."""
        conn = self._connect()
        cur = conn.cursor()
        
        fields = []
        vals = []
        
        if reply_text is not None:
            fields.append("reply_text = ?")
            vals.append(reply_text)
        if sql_query is not None:
            fields.append("sql_query = ?")
            vals.append(sql_query)
        if row_count is not None:
            fields.append("row_count = ?")
            vals.append(row_count)
        if ok is not None:
            fields.append("ok = ?")
            vals.append(1 if ok else 0)
        if error is not None:
            fields.append("error = ?")
            vals.append(error)
        if intent is not None:
            fields.append("intent = ?")
            vals.append(intent)
        
        if fields:
            vals.append(interaction_id)
            cur.execute(f"UPDATE interactions SET {', '.join(fields)} WHERE id = ?", vals)
            conn.commit()
        
        conn.close()
    
    def insert_service_call(
        self,
        interaction_id: int,
        service: str,
        url: str,
        ok: bool,
        status_code: Optional[int],
        latency_ms: int,
        request_json: Dict[str, Any],
        response_json: Any,
        error: str = "",
    ):
        """Insert a service call record."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO service_calls(interaction_id, ts_utc, service, url, ok, status_code, latency_ms, request_json, response_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            interaction_id,
            self._utc_now(),
            service,
            url,
            1 if ok else 0,
            status_code,
            latency_ms,
            json.dumps(self._redact(request_json), ensure_ascii=False),
            json.dumps(self._redact(response_json), ensure_ascii=False) if response_json is not None else None,
            error,
        ))
        conn.commit()
        conn.close()

    def insert_whatsapp_message(
        self,
        direction: str,
        phone_number: str,
        user_id: Optional[str],
        message_text: str,
        status: str,
        error: Optional[str] = None,
    ) -> int:
        """Insert a WhatsApp inbound/outbound audit record."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO whatsapp_messages(ts_utc, direction, phone_number, user_id, message_text, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            self._utc_now(),
            direction,
            phone_number,
            user_id,
            message_text,
            status,
            error,
        ))
        message_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        return message_id
    
    def query_history(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_utc: Optional[str] = None,
        end_utc: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query interaction history with filters."""
        conn = self._connect()
        cur = conn.cursor()
        
        where = []
        params = []
        
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)
        if start_utc:
            where.append("ts_utc >= ?")
            params.append(start_utc)
        if end_utc:
            where.append("ts_utc < ?")
            params.append(end_utc)
        
        sql = (
            "SELECT id, ts_utc, user_id, session_id, role, intent, raw_message, final_message, "
            "reply_text, sql_query, row_count, ok, error FROM interactions"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    
    def query_event(self, event_id: int) -> Dict[str, Any]:
        """Get event details including service calls."""
        conn = self._connect()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM interactions WHERE id = ?", (event_id,))
        inter = cur.fetchone()
        if not inter:
            conn.close()
            raise ValueError(f"Event {event_id} not found.")
        
        cur.execute("SELECT * FROM service_calls WHERE interaction_id = ? ORDER BY id ASC", (event_id,))
        calls = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM tool_executions WHERE interaction_id = ? ORDER BY id ASC", (event_id,))
        tool_calls = [dict(r) for r in cur.fetchall()]
        
        conn.close()
        return {"interaction": dict(inter), "service_calls": calls, "tool_executions": tool_calls}
    
    def insert_tool_execution(
        self,
        interaction_id: Optional[int],
        tool_name: str,
        user_id: str,
        role: Optional[str],
        is_write_action: bool,
        arguments_json: Dict[str, Any],
        result_json: Any,
        error: Optional[str],
        confirmation_token_id: Optional[str],
        ok: bool = True,
    ) -> int:
        """Insert a tool execution audit record."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tool_executions(
              ts_utc, interaction_id, tool_name, user_id, role, is_write_action,
              arguments_json, result_json, error, confirmation_token_id, ok
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._utc_now(),
                interaction_id,
                tool_name,
                user_id,
                role,
                1 if is_write_action else 0,
                json.dumps(self._redact(arguments_json), ensure_ascii=False),
                json.dumps(self._redact(result_json), ensure_ascii=False) if result_json is not None else None,
                error,
                confirmation_token_id,
                1 if ok else 0,
            ),
        )
        tool_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        return tool_id

    def search(self, q: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Full-text search interactions."""
        conn = self._connect()
        cur = conn.cursor()
        
        # Try FTS first, fallback to LIKE
        try:
            cur.execute("""
                SELECT i.id, i.ts_utc, i.user_id, i.session_id, i.raw_message, i.final_message, i.reply_text
                FROM interactions_fts f
                JOIN interactions i ON i.id = f.rowid
                WHERE interactions_fts MATCH ?
                ORDER BY i.id DESC
                LIMIT ?
            """, (q, limit))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception:
            like = f"%{q}%"
            cur.execute("""
                SELECT id, ts_utc, user_id, session_id, raw_message, final_message, reply_text
                FROM interactions
                WHERE raw_message LIKE ? OR final_message LIKE ? OR reply_text LIKE ?
                ORDER BY id DESC
                LIMIT ?
            """, (like, like, like, limit))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
    
    def parse_range(self, range_str: str) -> tuple[Optional[str], Optional[str]]:
        """Parse time range string to UTC ISO timestamps."""
        if not range_str:
            return None, None
        
        rs = range_str.strip().lower()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        
        if rs == "yesterday":
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
            end = start + timedelta(days=1)
            return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")
        
        if rs == "today":
            start = now.replace(hour=0, minute=0, second=0)
            end = start + timedelta(days=1)
            return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")
        
        if rs.endswith("d") and rs[:-1].isdigit():
            days = int(rs[:-1])
            start = now - timedelta(days=days)
            return start.isoformat().replace("+00:00", "Z"), now.isoformat().replace("+00:00", "Z")
        
        return None, None


# Global instance
_audit_repo = AuditRepository()


def audit_connect() -> sqlite3.Connection:
    """Legacy function for backward compatibility."""
    return _audit_repo._connect()


def audit_insert_interaction(*args, **kwargs) -> int:
    """Legacy function for backward compatibility."""
    return _audit_repo.insert_interaction(*args, **kwargs)


def audit_update_interaction(*args, **kwargs):
    """Legacy function for backward compatibility."""
    return _audit_repo.update_interaction(*args, **kwargs)


def audit_insert_service_call(*args, **kwargs):
    """Legacy function for backward compatibility."""
    return _audit_repo.insert_service_call(*args, **kwargs)



