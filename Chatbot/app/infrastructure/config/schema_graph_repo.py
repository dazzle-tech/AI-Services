"""Schema graph configuration repository."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None


class SchemaGraphRepository:
    """Repository for loading and managing schema graph configuration."""

    def __init__(self, schema_graph_path: Optional[str] = None, db_path: Optional[str] = None):
        self.schema_graph_path = schema_graph_path or settings.schema_graph_path
        self.db_path = db_path or settings.hospital_db_path

    def extract_from_sqlite(self, db_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Build a schema graph from a SQLite database."""
        db_path = db_path or self.db_path
        graph: Dict[str, Dict[str, Any]] = {}

        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [r[0] for r in cur.fetchall()]

            for table in tables:
                cur.execute(f"PRAGMA table_info({table});")
                cols = [r[1] for r in cur.fetchall()]

                cur.execute(f"PRAGMA foreign_key_list({table});")
                fks = [
                    {"from": r[3], "to_table": r[2], "to_col": r[4]}
                    for r in cur.fetchall()
                ]

                graph[table] = {"columns": cols, "foreign_keys": fks}

            conn.close()
            logger.info("✅ Extracted SQLite schema graph with %d tables.", len(graph))
        except Exception as e:
            logger.warning("⚠️ Failed to extract SQLite schema graph: %s", e)

        return graph

    def extract_from_postgresql(self) -> Dict[str, Dict[str, Any]]:
        """Build a schema graph from PostgreSQL (information_schema)."""
        if psycopg2 is None:
            raise ImportError("psycopg2 is required for PostgreSQL schema extraction")

        graph: Dict[str, Dict[str, Any]] = {}
        schema = (settings.db_schema or "public").strip() or "public"

        conn = psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            options=f"-c search_path={schema}",
        )
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
                ORDER BY table_name;
                """,
                (schema,),
            )
            tables = [r[0] for r in cur.fetchall()]

            for table in tables:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position;
                    """,
                    (schema, table),
                )
                cols = [r[0] for r in cur.fetchall()]

                cur.execute(
                    """
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu
                        ON ccu.constraint_name = tc.constraint_name
                        AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_schema = %s
                        AND tc.table_name = %s;
                    """,
                    (schema, table),
                )
                fks = [
                    {"from": r[0], "to_table": r[1], "to_col": r[2]}
                    for r in cur.fetchall()
                ]

                graph[table] = {"columns": cols, "foreign_keys": fks}

            logger.info("✅ Extracted PostgreSQL schema graph with %d tables.", len(graph))
        finally:
            conn.close()

        return graph

    def extract_from_access_control(self) -> Dict[str, Dict[str, Any]]:
        """
        Build a schema graph from access_control.json allowed_schema entries.

        Fallback when DB schema extraction isn't possible.
        Relationships are not available, so foreign_keys are empty.
        """
        path = settings.access_control_path
        if not os.path.exists(path):
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("⚠️ Failed to load access_control.json for schema graph fallback: %s", e)
            return {}

        allowed_schemas: list[dict] = []

        # Shared-policy format
        if isinstance(data, dict) and isinstance(data.get("allowed_schema"), dict):
            allowed_schemas.append(data["allowed_schema"])

        # Nested users format
        nested_users = data.get("users") if isinstance(data, dict) else None
        if isinstance(nested_users, dict):
            for ucfg in nested_users.values():
                if isinstance(ucfg, dict) and isinstance(ucfg.get("allowed_schema"), dict):
                    allowed_schemas.append(ucfg["allowed_schema"])

        # Top-level per-user format
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, dict) and isinstance(v.get("allowed_schema"), dict):
                    allowed_schemas.append(v["allowed_schema"])

        graph: Dict[str, Dict[str, Any]] = {}
        for schema in allowed_schemas:
            for table, details in schema.items():
                cols = details.get("columns", []) if isinstance(details, dict) else []
                if table not in graph:
                    graph[table] = {"columns": list(cols), "foreign_keys": []}
                else:
                    existing = set(graph[table].get("columns", []))
                    for c in cols:
                        if c not in existing:
                            graph[table]["columns"].append(c)

        if graph:
            logger.info("✅ Built schema graph fallback from access_control.json with %d tables.", len(graph))

        return graph

    # Backward-compatible name (older code may still call it)
    def extract_from_db(self, db_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        return self.extract_from_sqlite(db_path=db_path)

    def _expected_table_count_from_access_control(self) -> int:
        try:
            return len(self.extract_from_access_control())
        except Exception:
            return 0

    def _should_rebuild_cached_graph(self, cached_graph: Dict[str, Any]) -> bool:
        if not isinstance(cached_graph, dict) or not cached_graph:
            return True

        if os.getenv("SCHEMA_GRAPH_FORCE_REBUILD", "").strip().lower() in {"1", "true", "yes"}:
            return True

        db_type = (settings.db_type or "sqlite").lower()
        cached_table_count = len(cached_graph)

        # In PostgreSQL mode, a tiny cached graph is almost certainly from SQLite/mock.
        if db_type == "postgresql" and cached_table_count < 10:
            return True

        # Only apply access-control size heuristics in PostgreSQL mode. In SQLite mode
        # the local/mock DB may intentionally contain a small subset of tables.
        if db_type == "postgresql":
            expected = self._expected_table_count_from_access_control()
            if expected and cached_table_count < max(10, int(expected * 0.3)):
                return True

        return False

    def load_or_create(self) -> Dict[str, Dict[str, Any]]:
        """Load schema graph from cache or (re)build it."""
        if os.path.exists(self.schema_graph_path):
            try:
                with open(self.schema_graph_path, "r", encoding="utf-8") as f:
                    graph = json.load(f)
                    if isinstance(graph, dict) and graph and not self._should_rebuild_cached_graph(graph):
                        logger.info("🧠 Loaded cached schema graph from %s", self.schema_graph_path)
                        return graph
            except Exception as e:
                logger.warning("⚠️ Failed to load cached schema graph: %s", e)

        logger.info("🛠️ Building new schema graph...")
        db_type = (settings.db_type or "sqlite").lower()
        graph: Dict[str, Dict[str, Any]] = {}

        if db_type == "postgresql":
            try:
                graph = self.extract_from_postgresql()
            except Exception as e:
                logger.warning("⚠️ Failed to extract PostgreSQL schema graph: %s", e)

        if not graph:
            graph = self.extract_from_sqlite()

        if not graph:
            graph = self.extract_from_access_control()

        try:
            os.makedirs(os.path.dirname(self.schema_graph_path) or ".", exist_ok=True)
            with open(self.schema_graph_path, "w", encoding="utf-8") as f:
                json.dump(graph, f, indent=2)
            logger.info("💾 Saved schema graph to %s", self.schema_graph_path)
        except Exception as e:
            logger.warning("⚠️ Could not save schema graph: %s", e)

        return graph


# Global instance
_schema_graph_repo = SchemaGraphRepository()


def load_or_create_schema_graph() -> Dict[str, Dict[str, Any]]:
    """Legacy function for backward compatibility."""
    return _schema_graph_repo.load_or_create()
