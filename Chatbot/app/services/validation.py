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
        access_data = self.access_control_repo.load()
        if user_id not in access_data:
            raise ValueError(f"User {user_id} not found in access_control.json")
        
        user_access = access_data[user_id]
        sql_clean = " ".join(sql.strip().lower().splitlines())
        issues: List[str] = []
        
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
        
        # Column validation (simplified) - skip for audit tables
        if not uses_audit_db:
            select_match = re.search(r"select\s+(.*?)\s+from", sql_clean, re.DOTALL)
            if select_match:
                raw_cols = select_match.group(1)
                if raw_cols.strip() != "*":
                    columns = [
                        c.strip().split(".")[-1].split(" as ")[0]
                        for c in raw_cols.split(",")
                        if c.strip()
                    ]
                    all_cols = [c for t in allowed_schema.values() for c in t["columns"]]
                    for col in columns:
                        if re.match(r"^[a-z_][a-z0-9_]*$", col):
                            allowed = any(col in allowed_schema[t]["columns"] for t in allowed_schema)
                            if not allowed:
                                suggestion = get_close_matches(col, all_cols, n=1, cutoff=0.7)
                                msg = f"❌ Column '{col}' not allowed."
                                if suggestion:
                                    msg += f" Did you mean '{suggestion[0]}'?"
                                issues.append(msg)
        
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


# Global instance
_validation_service = ValidationService()

