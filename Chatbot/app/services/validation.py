"""SQL validation and execution service."""
import re
import sqlparse
import logging
from typing import Dict, Any, List, Optional
from difflib import get_close_matches
from app.infrastructure.db.hospital_repo import HospitalRepository
from app.infrastructure.db.audit_repo import AuditRepository
from app.infrastructure.config.access_control_repo import AccessControlRepository

logger = logging.getLogger(__name__)

FORBIDDEN_KEYWORDS = {"drop", "alter", "truncate", "grant", "revoke"}

# Audit database tables (stored in medai_audit.db, not hospital.db)
AUDIT_TABLES = {"interactions", "service_calls"}

# Common SQL keywords that should not be treated as table aliases
SQL_KEYWORDS = {
    "as", "on", "using", "where", "group", "by", "order", "limit", "offset",
    "inner", "left", "right", "full", "cross", "join", "union", "all",
    "having", "distinct", "select", "from",
}


class ValidationService:
    """Service for validating and executing SQL queries."""
    
    def __init__(
        self,
        hospital_repo: Optional[HospitalRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        access_control_repo: Optional[AccessControlRepository] = None,
    ):
        self.hospital_repo = hospital_repo or HospitalRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.access_control_repo = access_control_repo or AccessControlRepository()
    
    def validate_and_execute(self, user_id: str, sql: str, *, _is_retry: bool = False) -> Dict[str, Any]:
        """
        Validate and execute SQL query.
        
        Args:
            user_id: User ID
            sql: SQL query string
            _is_retry: Internal flag for retry logic
            
        Returns:
            Validation result dictionary
        """
        logger.info(f"🧩 Starting validation for SQL: {sql}")
        
        # Load access control
        user_access = self.access_control_repo.get_user_access(user_id)
        if not user_access:
            raise ValueError(f"User {user_id} not found in access_control.json")
        sql_clean = " ".join(sql.strip().lower().splitlines())
        issues: List[str] = []

        # Block unresolved placeholders early (prevents SQL syntax errors like "WHERE p.id = %s").
        if re.search(r"%s", sql, flags=re.IGNORECASE) or re.search(r"=\s*\?", sql_clean):
            issues.append("❌ SQL contains unresolved parameter placeholders (%s or ?). Please inline known values.")
        
        # Extract operation
        operation = self._extract_operation(sql)
        allowed_ops_user = user_access.get("allowed_operations", ["SELECT"])
        
        # Check operation
        if operation not in allowed_ops_user:
            issues.append(
                f"❌ Operation '{operation}' not allowed for role '{user_access.get('role', 'unknown')}'."
            )
        
        # Check forbidden keywords
        for word in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{word}\b", sql_clean):
                issues.append(f"❌ Forbidden keyword detected: {word.upper()}")
        
        # SQL parse check
        try:
            parsed = sqlparse.parse(sql)
            if not parsed:
                issues.append("❌ Invalid SQL syntax.")
        except Exception as e:
            issues.append(f"❌ SQL parsing failed: {e}")
        
        allowed_schema = user_access.get("allowed_schema", {})
        restrictions = user_access.get("restrictions", {})
        
        # Table validation
        tables = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b(?!\s*\()", sql_clean)
        found_tables = set(tables)
        
        # Check if query targets audit database tables (must be defined early)
        uses_audit_db = any(table in AUDIT_TABLES for table in found_tables)
        
        for table in found_tables:
            # Allow audit tables (interactions, service_calls) without schema check
            if table in AUDIT_TABLES:
                continue
            if table not in allowed_schema:
                suggestion = get_close_matches(table, list(allowed_schema.keys()), n=1, cutoff=0.7)
                msg = f"❌ Table '{table}' not allowed."
                if suggestion:
                    msg += f" Did you mean '{suggestion[0]}'?"
                issues.append(msg)
        
        # Column validation - skip for audit tables
        if not uses_audit_db:
            self._validate_column_references(sql_clean, allowed_schema, found_tables, issues)
        
        # Nested query restriction
        if not restrictions.get("allow_nested_queries", False) and "select" in sql_clean[6:]:
            issues.append("❌ Nested queries are not allowed for this role.")
        
        if issues:
            logger.warning(f"⚠️ Validation failed with {len(issues)} issue(s).")
            return {
                "valid": False,
                "message": " | ".join(issues),
                "rows": [],
                "row_count": 0,
            }
        
        # Execute query - route to appropriate database
        logger.info("✅ Validation passed. Proceeding to execution.")
        try:
            # Check if query targets audit database
            tables = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b(?!\s*\()", sql_clean)
            uses_audit_db = any(table in AUDIT_TABLES for table in tables)
            
            if uses_audit_db:
                logger.info("📊 Query targets audit database (interactions/service_calls)")
                # Execute against audit database
                conn = self.audit_repo._connect()
                cur = conn.cursor()
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
            else:
                # Execute against hospital database
                logger.info(f"🔍 [VALIDATION] Executing query against hospital database")
                logger.debug(f"📜 [VALIDATION] SQL to execute (first 500 chars):\n{sql[:500]}...")
                rows = self.hospital_repo.execute_query(sql)
                logger.info(f"📊 [VALIDATION] Query returned {len(rows)} row(s)")
            
            return {
                "valid": True,
                "message": f"✅ SQL '{operation}' validated and executed successfully.",
                "rows": rows,
                "row_count": len(rows),
            }
        except Exception as e:
            logger.error(f"❌ Database execution error: {e}")
            return {
                "valid": False,
                "message": f"SQL Execution Error: {e}",
                "rows": [],
                "row_count": 0,
            }
    
    def _extract_operation(self, sql: str) -> str:
        """Extract SQL operation."""
        if not sql or not sql.strip():
            return "UNKNOWN"
        m = re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", sql, re.IGNORECASE)
        return m.group(1).upper() if m else "UNKNOWN"

    def _validate_column_references(
        self,
        sql_clean: str,
        allowed_schema: Dict[str, Any],
        found_tables: set,
        issues: List[str],
    ) -> None:
        """
        Validate column usage against the tables actually referenced by the query.

        This stays regex-based for speed/simplicity, but validates *qualified* references
        (alias.column) against the alias's table, which prevents false passes like `e.id`
        when `id` exists in some other allowed table.
        """
        # Build alias -> table mapping from FROM/JOIN clauses (skip subqueries like FROM (...))
        alias_to_table: Dict[str, str] = {}
        for m in re.finditer(
            r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b(?!\s*\()"
            r"(?:\s+(?:as\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?",
            sql_clean,
            flags=re.IGNORECASE,
        ):
            table = (m.group(1) or "").lower()
            alias = (m.group(2) or "").lower()
            if not table:
                continue
            if alias and alias in SQL_KEYWORDS:
                alias = ""
            alias_to_table[alias or table] = table

        referenced_tables = {t for t in alias_to_table.values() if t in allowed_schema}
        if not referenced_tables:
            return

        # Validate qualified references like e.created_at, p.key, etc.
        qualified_refs = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*|\*)\b", sql_clean)
        for alias, col in qualified_refs:
            alias_l = alias.lower()
            col_l = col.lower()
            if col_l == "*":
                continue

            table = alias_to_table.get(alias_l)
            if not table or table not in allowed_schema:
                continue

            table_cols = {c.lower() for c in allowed_schema[table].get("columns", [])}
            if col_l not in table_cols:
                suggestion = get_close_matches(col_l, sorted(table_cols), n=1, cutoff=0.7)
                msg = f"❌ Column '{alias_l}.{col_l}' not allowed (table '{table}')."
                if suggestion:
                    msg += f" Did you mean '{alias_l}.{suggestion[0]}'?"
                issues.append(msg)

        # Validate simple unqualified SELECT columns against referenced tables only
        select_match = re.search(r"select\s+(.*?)\s+from", sql_clean, re.DOTALL)
        if not select_match:
            return

        raw_cols = (select_match.group(1) or "").strip()
        if not raw_cols or raw_cols == "*":
            return

        combined_cols = set()
        for table in referenced_tables:
            combined_cols.update({c.lower() for c in allowed_schema[table].get("columns", [])})

        columns = [
            c.strip().split(".")[-1].split(" as ")[0].strip()
            for c in raw_cols.split(",")
            if c.strip()
        ]
        for col in columns:
            col_l = col.lower()
            if not re.match(r"^[a-z_][a-z0-9_]*$", col_l):
                continue
            if col_l in SQL_KEYWORDS:
                continue
            if col_l not in combined_cols:
                suggestion = get_close_matches(col_l, sorted(combined_cols), n=1, cutoff=0.7)
                msg = f"❌ Column '{col_l}' not allowed for the referenced tables."
                if suggestion:
                    msg += f" Did you mean '{suggestion[0]}'?"
                issues.append(msg)


# Global instance
_validation_service = ValidationService()
