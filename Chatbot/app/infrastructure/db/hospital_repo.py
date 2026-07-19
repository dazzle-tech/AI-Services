"""Hospital database repository."""
import os
import sqlite3
import re
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import psycopg2 for PostgreSQL support
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("⚠️ psycopg2 not installed. PostgreSQL support unavailable. Install with: pip install psycopg2-binary")


class HospitalRepository:
    """Repository for executing queries against hospital database (SQLite or PostgreSQL)."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_type = settings.db_type.lower()
        self.db_path = db_path or settings.hospital_db_path
        
        if self.db_type == "postgresql" and not PSYCOPG2_AVAILABLE:
            raise ImportError("PostgreSQL support requires psycopg2. Install with: pip install psycopg2-binary")
    
    def _get_sqlite_connection(self):
        """Get SQLite connection."""
        if not os.path.exists(self.db_path):
            logger.error(f"❌ Database file not found: {self.db_path}")
            raise FileNotFoundError(f"Database file not found: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_postgresql_connection(self):
        """Get PostgreSQL connection."""
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL connections")
        
        conn = psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            options=f"-c search_path={settings.db_schema}"
        )
        return conn
    
    def _normalize_sql_for_db(self, sql: str) -> str:
        """
        Normalize SQL query for the target database type.
        Converts SQLite-style boolean checks to PostgreSQL-style when using PostgreSQL.
        
        Args:
            sql: Original SQL query
            
        Returns:
            Normalized SQL query
        """
        if self.db_type == "postgresql":
            # Convert SQLite boolean checks (column = 1) to PostgreSQL (column = TRUE)
            # Pattern: column_name = 1 or column_name = 0
            # Be careful to only match boolean column patterns, not numeric comparisons
            
            # Common boolean column names
            boolean_columns = [
                'is_valid', 'is_active', 'is_major', 'is_suspected', 
                'verified', 'activated', 'has_', 'can_', 'primary_insurance'
            ]
            
            normalized_sql = sql
            for col_pattern in boolean_columns:
                # Match: table.col = 1, col = 1, table.col = 0, col = 0
                # Use word boundaries to avoid matching inside other words
                pattern = rf'\b([a-zA-Z_][a-zA-Z0-9_]*\.)?{col_pattern}\s*=\s*1\b'
                replacement = r'\1' + col_pattern + ' = TRUE'
                normalized_sql = re.sub(pattern, replacement, normalized_sql, flags=re.IGNORECASE)
                
                pattern = rf'\b([a-zA-Z_][a-zA-Z0-9_]*\.)?{col_pattern}\s*=\s*0\b'
                replacement = r'\1' + col_pattern + ' = FALSE'
                normalized_sql = re.sub(pattern, replacement, normalized_sql, flags=re.IGNORECASE)
            
            return normalized_sql
        else:
            return sql
    
    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results as list of dictionaries.
        
        Args:
            sql: SQL query string
            
        Returns:
            List of row dictionaries
            
        Raises:
            FileNotFoundError: If SQLite database file doesn't exist
            sqlite3.Error: If SQLite execution fails
            psycopg2.Error: If PostgreSQL execution fails
        """
        # Normalize SQL for the target database
        normalized_sql = self._normalize_sql_for_db(sql)
        
        if self.db_type == "postgresql":
            return self._execute_postgresql_query(normalized_sql)
        else:
            return self._execute_sqlite_query(normalized_sql)
    
    def _execute_sqlite_query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute query against SQLite database."""
        conn = self._get_sqlite_connection()
        logger.info(f"📂 Connected to SQLite DB: {self.db_path}")
        
        try:
            cur = conn.cursor()
            logger.info(f"🧾 Executing SQL: {sql}")
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
            logger.info(f"✅ Query executed successfully. Returned {len(rows)} row(s).")
            return rows
        except sqlite3.Error as e:
            logger.error(f"❌ Database execution error: {e}")
            raise
        finally:
            conn.close()
            logger.info("🔒 Database connection closed.")
    
    def _execute_postgresql_query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute query against PostgreSQL database."""
        conn = self._get_postgresql_connection()
        logger.info(f"📂 Connected to PostgreSQL DB: {settings.db_host}:{settings.db_port}/{settings.db_name}")
        
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            logger.info(f"🧾 Executing SQL (first 200 chars): {sql[:200]}...")
            logger.debug(f"🧾 Full SQL:\n{sql}")
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
            logger.info(f"✅ Query executed successfully. Returned {len(rows)} row(s).")
            if rows:
                logger.debug(f"📋 First row keys: {list(rows[0].keys())[:10]}...")
            else:
                logger.warning(f"⚠️ Query returned 0 rows. SQL:\n{sql[:500]}...")
            return rows
        except Exception as e:
            logger.error(f"❌ Database execution error: {e}")
            logger.error(f"❌ SQL that failed:\n{sql}")
            raise
        finally:
            conn.close()
            logger.info("🔒 Database connection closed.")
    
    def fetch_patient_id_by_name(self, name: str) -> Optional[str]:
        """
        Lookup patient ID by name.
        
        Args:
            name: Patient name
            
        Returns:
            Patient key (ID) or None if not found
        """
        try:
            full_name_expr = (
                "trim(coalesce(first_name, '') || ' ' || coalesce(second_name, '') || ' ' || "
                "coalesce(third_name, '') || ' ' || coalesce(last_name, ''))"
            )
            simple_name_expr = (
                "trim(coalesce(first_name, '') || ' ' || coalesce(last_name, ''))"
            )
            if self.db_type == "postgresql":
                sql = (
                    f"SELECT id FROM patients WHERE (lower({full_name_expr}) = lower(%s) "
                    f"OR lower({simple_name_expr}) = lower(%s)) LIMIT 1"
                )
                conn = self._get_postgresql_connection()
                cur = conn.cursor()
                cur.execute(sql, (name, name))
                row = cur.fetchone()
                conn.close()
                return row[0] if row else None
            else:
                sql = (
                    f"SELECT id FROM patients WHERE (lower({full_name_expr}) = lower(?) "
                    f"OR lower({simple_name_expr}) = lower(?)) LIMIT 1"
                )
                conn = self._get_sqlite_connection()
                cur = conn.cursor()
                cur.execute(sql, (name, name))
                row = cur.fetchone()
                conn.close()
                return row[0] if row else None
        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch patient ID by name '{name}': {e}")
            return None


    def fetch_patient_id_by_medical_record_number(self, medical_record_number: str) -> Optional[str]:
        """
        Lookup patient ID by medical record number.
        """
        try:
            identifier = str(medical_record_number)
            if self.db_type == "postgresql":
                sql = "SELECT id FROM patients WHERE CAST(medical_record_number AS TEXT) = %s LIMIT 1"
                conn = self._get_postgresql_connection()
                cur = conn.cursor()
                cur.execute(sql, (identifier,))
                row = cur.fetchone()
                conn.close()
                return str(row[0]) if row else None
            else:
                sql = "SELECT id FROM patients WHERE CAST(medical_record_number AS TEXT) = ? LIMIT 1"
                conn = self._get_sqlite_connection()
                cur = conn.cursor()
                cur.execute(sql, (identifier,))
                row = cur.fetchone()
                conn.close()
                return str(row[0]) if row else None
        except Exception as e:
            logger.warning(f"Failed to fetch patient ID by medical record number '{medical_record_number}': {e}")
            return None

    def fetch_phone_by_mrn(self, medical_record_number: str) -> Optional[str]:
        """
        Fetch the phone number on file for a patient MRN.

        Checks common phone column names on the patients table.
        """
        mrn = str(medical_record_number).strip()
        phone_columns = [
            "primary_mobile_number",
            "mobile_number",
            "phone_number",
            "home_phone",
            "work_phone",
        ]
        for col in phone_columns:
            try:
                if self.db_type == "postgresql":
                    sql = (
                        f"SELECT {col} FROM patients "
                        "WHERE CAST(medical_record_number AS TEXT) = %s "
                        f"AND {col} IS NOT NULL AND TRIM(CAST({col} AS TEXT)) != '' "
                        "LIMIT 1"
                    )
                    conn = self._get_postgresql_connection()
                    cur = conn.cursor()
                    cur.execute(sql, (mrn,))
                    row = cur.fetchone()
                    conn.close()
                else:
                    sql = (
                        f"SELECT {col} FROM patients "
                        "WHERE CAST(medical_record_number AS TEXT) = ? "
                        f"AND {col} IS NOT NULL AND TRIM({col}) != '' "
                        "LIMIT 1"
                    )
                    conn = self._get_sqlite_connection()
                    cur = conn.cursor()
                    cur.execute(sql, (mrn,))
                    row = cur.fetchone()
                    conn.close()
                if row and row[0]:
                    return str(row[0]).strip()
            except Exception as exc:
                logger.debug("Phone lookup via %s failed for MRN %s: %s", col, mrn, exc)
                continue
        return None


# Global instance
_hospital_repo = HospitalRepository()


def fetch_patient_id_by_name(name: str) -> Optional[str]:
    """Legacy function for backward compatibility."""
    return _hospital_repo.fetch_patient_id_by_name(name)


def fetch_patient_id_by_medical_record_number(medical_record_number: str) -> Optional[str]:
    """Legacy function for backward compatibility."""
    return _hospital_repo.fetch_patient_id_by_medical_record_number(medical_record_number)
