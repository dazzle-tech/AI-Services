"""Registered users store for WhatsApp phone → user_id mapping."""
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    PSYCOPG2_AVAILABLE = False
    logger.warning(
        "⚠️ psycopg2 not installed. PostgreSQL support unavailable for registered users store. "
        "Install with: pip install psycopg2-binary"
    )


class RegisteredUsersRepository:
    """SQL-backed repository for phone-number identity mappings."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_type = (settings.db_type or "sqlite").lower()
        self.db_path = db_path or settings.registered_users_db_path
        if self.db_type == "postgresql" and not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "PostgreSQL support requires psycopg2-binary. Install with: pip install psycopg2-binary"
            )
        self._init_db()

    def _get_sqlite_connection(self):
        if not os.path.exists(self.db_path):
            dirname = os.path.dirname(self.db_path)
            if dirname and not os.path.exists(dirname):
                os.makedirs(dirname, exist_ok=True)
        conn = __import__("sqlite3").connect(self.db_path, check_same_thread=False)
        conn.row_factory = __import__("sqlite3").Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _get_postgresql_connection(self):
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL connections")
        conn = psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            options=f"-c search_path={settings.db_schema}",
        )
        return conn

    def _connect(self):
        if self.db_type == "postgresql":
            conn = self._get_postgresql_connection()
        else:
            conn = self._get_sqlite_connection()
        return conn

    def _placeholder(self) -> str:
        return "%s" if self.db_type == "postgresql" else "?"

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _init_db(self) -> None:
        conn = self._connect()
        cur = conn.cursor()

        if self.db_type == "postgresql":
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_users (
                  phone_number TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  active BOOLEAN NOT NULL DEFAULT TRUE,
                  registered_at TIMESTAMPTZ NOT NULL,
                  registered_by TEXT,
                  otp_verified BOOLEAN NOT NULL DEFAULT FALSE
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_registered_users_user_id ON registered_users(user_id);"
            )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_users (
                  phone_number TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  active INTEGER NOT NULL DEFAULT 1,
                  registered_at TEXT NOT NULL,
                  registered_by TEXT,
                  otp_verified INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_registered_users_user_id ON registered_users(user_id);"
            )

        conn.commit()
        conn.close()
        logger.info("Registered users store ready: %s (db_type=%s)", self.db_path, self.db_type)

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        d = dict(row)
        d["active"] = bool(d.get("active"))
        d["otp_verified"] = bool(d.get("otp_verified"))
        return d

    def get_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM registered_users WHERE phone_number = {self._placeholder()}",
            (phone_number,),
        )
        row = cur.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def upsert(
        self,
        phone_number: str,
        user_id: str,
        role: str,
        *,
        registered_by: Optional[str] = None,
        active: bool = True,
        otp_verified: bool = False,
    ) -> None:
        conn = self._connect()
        cur = conn.cursor()
        params = [
            phone_number,
            user_id,
            role,
            active if self.db_type == "postgresql" else (1 if active else 0),
            self._utc_now(),
            registered_by,
            otp_verified if self.db_type == "postgresql" else (1 if otp_verified else 0),
        ]

        if self.db_type == "postgresql":
            cur.execute(
                """
                INSERT INTO registered_users(
                  phone_number, user_id, role, active, registered_at, registered_by, otp_verified
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(phone_number) DO UPDATE SET
                  user_id = EXCLUDED.user_id,
                  role = EXCLUDED.role,
                  active = EXCLUDED.active,
                  registered_by = EXCLUDED.registered_by,
                  otp_verified = EXCLUDED.otp_verified
                """,
                params,
            )
        else:
            placeholders = ", ".join([self._placeholder()] * 7)
            cur.execute(
                f"INSERT INTO registered_users(
                  phone_number, user_id, role, active, registered_at, registered_by, otp_verified
                ) VALUES ({placeholders})
                ON CONFLICT(phone_number) DO UPDATE SET
                  user_id = excluded.user_id,
                  role = excluded.role,
                  active = excluded.active,
                  registered_by = excluded.registered_by,
                  otp_verified = excluded.otp_verified
                ",
                params,
            )

        conn.commit()
        conn.close()

    def set_active(self, phone_number: str, active: bool) -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE registered_users SET active = {self._placeholder()} WHERE phone_number = {self._placeholder()}",
            (active if self.db_type == "postgresql" else (1 if active else 0), phone_number),
        )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def set_otp_verified(self, phone_number: str, verified: bool = True) -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE registered_users SET otp_verified = {self._placeholder()} WHERE phone_number = {self._placeholder()}",
            (verified if self.db_type == "postgresql" else (1 if verified else 0), phone_number),
        )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def list_all(self, *, active_only: bool = False) -> List[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        if active_only:
            cur.execute(
                f"SELECT * FROM registered_users WHERE active = {self._placeholder()} ORDER BY registered_at DESC",
                (True if self.db_type == "postgresql" else 1,),
            )
        else:
            cur.execute("SELECT * FROM registered_users ORDER BY registered_at DESC")
        rows = [self._row_to_dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
