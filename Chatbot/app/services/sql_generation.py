"""SQL generation service - encapsulates SQL generation logic."""
import re
import logging
from typing import Dict, Any, Set, Optional, Any
from app.infrastructure.llm.llm_client import get_llm_client
from app.infrastructure.config.access_control_repo import AccessControlRepository
from app.infrastructure.config.schema_graph_repo import SchemaGraphRepository
from app.core.config import settings

logger = logging.getLogger(__name__)


class SQLGenerationService:
    """Service for generating SQL queries from natural language."""
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        access_control_repo: Optional[AccessControlRepository] = None,
        schema_graph_repo: Optional[SchemaGraphRepository] = None,
    ):
        # Use OpenAI for SQL generation if provider is openai, otherwise Ollama
        if settings.llm_provider == "openai":
            model = settings.openai_sql_gen_model
        else:
            model = settings.sql_gen_model
        self.llm_client = llm_client or get_llm_client(model=model)
        self.access_control_repo = access_control_repo or AccessControlRepository()
        self.schema_graph_repo = schema_graph_repo or SchemaGraphRepository()
        self.schema_graph = self.schema_graph_repo.load_or_create()
        self.field_index = self._build_field_index(self.schema_graph)
    
    def _build_field_index(self, graph: Dict[str, Dict[str, Any]]) -> Dict[str, Set[str]]:
        """Build reverse index: column -> set(tables containing it)."""
        idx: Dict[str, Set[str]] = {}
        for t, info in graph.items():
            for c in info.get("columns", []):
                idx.setdefault(c.lower(), set()).add(t)
        return idx
    
    def generate_sql(self, user_id: str, text: str) -> str:
        """
        Generate SQL query from natural language text.
        
        Args:
            user_id: User ID
            text: Natural language query
            
        Returns:
            Generated SQL query string
        """
        # Load access control
        access_data = self.access_control_repo.load()
        if user_id not in access_data:
            raise ValueError(f"User {user_id} not in access_control.json")
        
        user_access = access_data[user_id]
        
        # Detect relevant tables from user query
        initial_tables = self._detect_relevant_tables_from_text(text)
        
        # If no tables detected, use intelligent fallback based on common keywords
        if not initial_tables:
            initial_tables = self._fallback_table_detection(text, user_access["allowed_schema"])
        
        # Expand via graph (but limit expansion to prevent explosion)
        expanded_tables = self._expand_tables_by_graph(initial_tables)
        
        # Limit total tables to prevent huge prompts (max 20 tables)
        if len(expanded_tables) > 20:
            logger.warning(f"⚠️ Too many tables detected ({len(expanded_tables)}), limiting to 20 most relevant")
            # Keep initial tables + most connected tables
            expanded_tables = self._limit_tables_intelligently(initial_tables, expanded_tables, max_tables=20)
        
        reduced_graph = self._restrict_schema_context(expanded_tables)
        
        logger.info(f"📊 Table filtering: {len(initial_tables)} initial → {len(expanded_tables)} expanded → {len(reduced_graph)} final tables")
        
        # Check if query is about chatbot interactions/services
        text_lower = text.lower()
        chatbot_service_keywords = [
            'services you have provided', 'services you provided', 'services provided',
            'queries you', 'interactions', 'chatbot', 'user queries', 'user questions',
            'what users asked', 'user requests'
        ]
        is_chatbot_query = any(keyword in text_lower for keyword in chatbot_service_keywords)
        
        # Build schema string
        reduced_access = {
            "allowed_schema": {
                t: user_access["allowed_schema"][t]
                for t in reduced_graph.keys()
                if t in user_access["allowed_schema"]
            }
        }
        
        # If query is about chatbot services, add interactions table schema
        if is_chatbot_query:
            reduced_access["allowed_schema"]["interactions"] = {
                "columns": [
                    "id", "ts_utc", "user_id", "session_id", "role", "intent",
                    "approved", "raw_message", "final_message", "reply_text",
                    "sql_query", "row_count", "ok", "error"
                ]
            }
            logger.info("📊 Added interactions table schema for chatbot services query")
        
        relationships = {}
        for t, info in reduced_graph.items():
            for fk in info.get("foreign_keys", []):
                relationships[f"{t}.{fk['from']}"] = f"{fk['to_table']}.{fk['to_col']}"
        
        schema_str = self._build_schema_string_from_access(reduced_access, relationships)
        ops = ", ".join(user_access.get("allowed_operations", ["SELECT"]))
        allow_nested = bool(user_access.get("restrictions", {}).get("allow_nested_queries", False))
        graph_context = self._build_schema_context_for_prompt(reduced_graph)
        
        # Build prompt
        prompt = self._build_llm_prompt(text, ops, schema_str, allow_nested, graph_context, is_chatbot_query)
        
        # Call LLM
        sql_query = self.llm_client.generate(prompt)
        sql_query = self._normalize_sql(sql_query)
        
        if not self._starts_with_valid_op(sql_query):
            raise ValueError("Generated SQL invalid or empty")
        
        return sql_query
    
    def _detect_relevant_tables_from_text(self, text: str) -> Set[str]:
        """Detect relevant tables from text using field index and keyword matching."""
        text_lower = text.lower()
        tokens = re.findall(r"[a-zA-Z_]+", text_lower)
        tables = set()
        
        # Special case: Check if query is about chatbot interactions/services
        # Keywords: "services you have provided", "services provided", "queries", "interactions", "chatbot"
        chatbot_service_keywords = [
            'services you have provided', 'services you provided', 'services provided',
            'queries you', 'interactions', 'chatbot', 'user queries', 'user questions',
            'what users asked', 'user requests'
        ]
        is_chatbot_query = any(keyword in text_lower for keyword in chatbot_service_keywords)
        
        if is_chatbot_query:
            # Return empty set - we'll handle this specially in the prompt
            logger.info("🔍 Detected chatbot interactions query - will use interactions table")
            return set()  # Special handling needed
        
        # Method 1: Field-based detection (existing)
        for tok in tokens:
            if tok in self.field_index:
                tables.update(self.field_index[tok])
        
        # Method 2: Direct table name matching (e.g., "patient", "encounter", "diagnosis")
        # Map common keywords to table prefixes
        keyword_to_prefix = {
            'patient': 'ap_patient',
            'encounter': 'ap_encounter',
            'visit': 'ap_encounter',
            'admission': 'ap_encounter',
            'diagnosis': 'ap_patient_diagnose',
            'diagnose': 'ap_patient_diagnose',
            'allergy': 'ap_patient_allergies',
            'allergies': 'ap_patient_allergies',
            'medication': 'ap_prescription_medications',
            'medications': 'ap_prescription_medications',
            'prescription': 'ap_prescription',
            'drug': 'ap_drug_order',
            'observation': 'ap_patient_observation',
            'vital': 'ap_patient_observation',
            'insurance': 'ap_patient_insurance',
            'problem': 'ap_patient_problem',
            'chronic': 'ap_patient_problem',
        }
        
        for keyword, table_prefix in keyword_to_prefix.items():
            if keyword in text_lower:
                # Find all tables starting with this prefix
                for table_name in self.schema_graph.keys():
                    if table_name.startswith(table_prefix):
                        tables.add(table_name)
        
        return tables
    
    def _fallback_table_detection(self, text: str, allowed_schema: Dict[str, Any]) -> Set[str]:
        """Intelligent fallback when no tables detected - use common patient-related tables."""
        text_lower = text.lower()
        fallback_tables = set()
        
        # Always include core patient table
        if "ap_patient" in allowed_schema:
            fallback_tables.add("ap_patient")
        
        # Add encounter if query mentions time/date/admission/discharge
        if any(word in text_lower for word in ['admission', 'discharge', 'encounter', 'visit', 'admitted', 'discharged', 'date', 'recent', 'last']):
            if "ap_encounter" in allowed_schema:
                fallback_tables.add("ap_encounter")
        
        # Add diagnosis if query mentions diagnosis/condition
        if any(word in text_lower for word in ['diagnosis', 'diagnose', 'condition', 'disease', 'illness']):
            if "ap_patient_diagnose" in allowed_schema:
                fallback_tables.add("ap_patient_diagnose")
        
        # If still empty, return just patient table (minimal fallback)
        if not fallback_tables and "ap_patient" in allowed_schema:
            fallback_tables.add("ap_patient")
        
        return fallback_tables
    
    def _limit_tables_intelligently(self, initial_tables: Set[str], expanded_tables: Set[str], max_tables: int = 20) -> Set[str]:
        """Limit tables intelligently by keeping initial + most connected tables."""
        if len(expanded_tables) <= max_tables:
            return expanded_tables
        
        # Always keep initial tables
        result = set(initial_tables)
        
        # Calculate connectivity score for remaining tables
        remaining = expanded_tables - initial_tables
        table_scores = {}
        
        for table in remaining:
            score = 0
            # Count foreign key connections to initial tables
            if table in self.schema_graph:
                for fk in self.schema_graph[table].get("foreign_keys", []):
                    if fk["to_table"] in initial_tables:
                        score += 2
                    if fk["to_table"] in result:
                        score += 1
                # Count reverse connections (tables that reference this one)
                for other_table, info in self.schema_graph.items():
                    if other_table in initial_tables:
                        for fk in info.get("foreign_keys", []):
                            if fk["to_table"] == table:
                                score += 2
        
            table_scores[table] = score
        
        # Add highest scoring tables until we reach max
        sorted_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)
        for table, score in sorted_tables:
            if len(result) >= max_tables:
                break
            result.add(table)
        
        return result
    
    def _expand_tables_by_graph(self, tables: Set[str]) -> Set[str]:
        """Expand tables by graph relationships."""
        expanded = set(tables)
        for t in list(tables):
            for fk in self.schema_graph.get(t, {}).get("foreign_keys", []):
                expanded.add(fk["to_table"])
            for other, info in self.schema_graph.items():
                for fk in info.get("foreign_keys", []):
                    if fk["to_table"] == t:
                        expanded.add(other)
        return expanded
    
    def _restrict_schema_context(self, tables: Set[str]) -> Dict[str, Dict[str, Any]]:
        """Return reduced schema graph."""
        return {t: self.schema_graph[t] for t in tables if t in self.schema_graph}
    
    def _build_schema_string_from_access(self, access_control: dict, relationships: dict = None) -> str:
        """Convert access schema to readable format."""
        parts = []
        for table, details in access_control["allowed_schema"].items():
            cols = ", ".join(details["columns"])
            parts.append(f"- {table}({cols})")
        
        if relationships:
            import json
            rels = json.dumps(relationships, indent=2)
            parts.append(f"\nKnown relationships:\n{rels}")
        
        return "\n".join(parts)
    
    def _build_schema_context_for_prompt(self, graph: Dict[str, Dict[str, Any]]) -> str:
        """Build compact schema description."""
        lines = []
        for t, info in graph.items():
            cols = info.get("columns", [])
            col_str = ", ".join(cols[:25]) + ("..." if len(cols) > 25 else "")
            lines.append(f"- {t}({col_str})")
            for fk in info.get("foreign_keys", []):
                lines.append(f"  ↳ {t}.{fk['from']} → {fk['to_table']}.{fk['to_col']}")
        return "\n".join(lines)
    
    def _build_llm_prompt(self, req_text: str, ops: str, schema_str: str, allow_nested: bool, graph_context: str = "", is_chatbot_query: bool = False) -> str:
        """Build LLM prompt for SQL generation."""
        nested_rule = (
            "- Nested queries are NOT allowed for this user; prefer JOIN ... ORDER BY ... LIMIT and simple WHERE filters.\n"
            if not allow_nested else
            "- Nested queries are allowed, but prefer JOIN ... ORDER BY ... LIMIT when equivalent.\n"
        )
        
        graph_note = f"\nSchema graph (tables, columns, and foreign keys):\n{graph_context}\n" if graph_context else ""
        
        return f"""
You are an expert SQL generator for PostgreSQL database. Generate ONLY valid PostgreSQL syntax.

CRITICAL PostgreSQL syntax rules:
- Use CURRENT_DATE - INTERVAL '1 day' for yesterday (or CURRENT_DATE - 1)
- Use CURRENT_DATE for today (or CURRENT_DATE)
- Use CURRENT_TIMESTAMP or NOW() for current timestamp
- Use date arithmetic: date_column - INTERVAL 'N days' or date_column - N (for days)
- Boolean columns use TRUE/FALSE, not 1/0 (e.g., is_valid = TRUE, not is_valid = 1)
- Use parameter placeholders %s for prepared statements (but in raw SQL, use literal values)
- String concatenation: use || or CONCAT() function
- Always use table aliases (e.g., FROM ap_patient p) and qualify column names (e.g., p.key, p.full_name)
- Always include WHERE p.is_valid = TRUE (or e.is_valid = TRUE) when querying ap_patient or ap_encounter tables
- Use double quotes for identifiers only if needed (usually lowercase identifiers work without quotes)
- Use single quotes for string literals
- TIMESTAMP CONVERSION: Admission date is e.created_at (millisecond timestamp), discharge date is e.discharge_at (millisecond timestamp)
  - To convert millisecond timestamp to date: TO_TIMESTAMP(e.created_at / 1000.0) for PostgreSQL
  - To compare with dates: TO_TIMESTAMP(e.created_at / 1000.0) >= CURRENT_DATE - INTERVAL '7 days'
  - For display: Use TO_CHAR(TO_TIMESTAMP(e.created_at / 1000.0), 'YYYY-MM-DD') AS admission_date

QUERY INTERPRETATION GUIDELINES:
1. "Recently" or "recent": 
   - Use ORDER BY date_column DESC LIMIT N (N=5-10) for most recent records
   - OR use date_column >= CURRENT_DATE - INTERVAL '90 days' for time-based filters (90 days is reasonable for "recently")
   - DO NOT use strict 7-day filters for "recently" - use 90 days or ORDER BY with LIMIT

2. "Last 2 weeks" or "past 2 weeks" (default filter for patient list queries):
   - When user asks for "all patients" or "list of patients" without specifying a date, use LAST 2 WEEKS as default
   - Filter by admission date: TO_TIMESTAMP(e.created_at / 1000.0) >= CURRENT_DATE - INTERVAL '14 days'
   - If querying ap_patient directly without encounter, use a reasonable date column or join with ap_encounter
   - Example: SELECT p.key AS patient_id, p.full_name, TO_CHAR(TO_TIMESTAMP(e.created_at / 1000.0), 'YYYY-MM-DD') AS admission_date FROM ap_patient p JOIN ap_encounter e ON p.key = e.patient_key WHERE e.is_valid = TRUE AND p.is_valid = TRUE AND TO_TIMESTAMP(e.created_at / 1000.0) >= CURRENT_DATE - INTERVAL '14 days' ORDER BY e.created_at DESC

3. "Last" or "most recent": 
   - Use ORDER BY date_column DESC LIMIT 1
   - No date filter needed, just order and limit

3. "Are all X Y?" questions:
   - This means "check if every X has property Y"
   - Use: SELECT COUNT(*) FROM table WHERE condition IS NULL (to find ones that don't have the property)
   - Or: SELECT COUNT(*) FROM table1 WHERE NOT EXISTS (SELECT 1 FROM table2 WHERE ...)
   - DO NOT use: SELECT COUNT(*) = (SELECT COUNT(*) ...) in SELECT clause
   - Example for "are all discharged": SELECT COUNT(*) FROM ap_patient p LEFT JOIN ap_encounter e ON e.patient_key = p.key AND e.is_valid = TRUE WHERE e.discharge_at != 0 AND p.is_valid = TRUE
   - IMPORTANT: Admission date is e.created_at (millisecond timestamp), NOT actual_start_date
   - Discharge date is e.discharge_at (millisecond timestamp when encounter is complete, 0 if not discharged)

4. "Admitted patients" or "last admitted patient" or "currently admitted":
   - Means patients currently in the hospital (encounters that are not yet discharged)
   - CRITICAL FOR POSTGRESQL: In this database, non-discharged patients have discharge_at = 0 (NOT NULL)
   - ALWAYS use: e.discharge_at = 0 (NOT e.discharge_at IS NULL)
   - DO NOT filter by encounter_type_lkey (it may be NULL in this database)
   - DO NOT filter by encounter_status_lkey (it uses numeric IDs, not text)
   - IMPORTANT: Admission date is stored in e.created_at (millisecond timestamp), NOT actual_start_date
   - Discharge date is e.discharge_at (millisecond timestamp when encounter is complete)
   - Primary criteria: e.discharge_at = 0 AND e.is_valid = TRUE AND p.is_valid = TRUE
   - Example: SELECT p.key AS patient_id, p.full_name, TO_CHAR(TO_TIMESTAMP(e.created_at / 1000.0), 'YYYY-MM-DD') AS admission_date FROM ap_patient p JOIN ap_encounter e ON p.key = e.patient_key WHERE e.discharge_at = 0 AND e.is_valid = TRUE AND p.is_valid = TRUE ORDER BY e.created_at DESC LIMIT 1
   - For "last admitted": Add ORDER BY e.created_at DESC LIMIT 1
   - To convert millisecond timestamp to date: Use TO_TIMESTAMP(e.created_at / 1000.0) for PostgreSQL

5. Patient identifier requirement:
   - When querying ap_patient table, ALWAYS include p.key AS patient_id in the SELECT clause
   - This enables the frontend to create clickable patient detail links
   - Use table alias 'p' for ap_patient (e.g., FROM ap_patient p)
   - Example: SELECT p.key AS patient_id, p.full_name, ... FROM ap_patient p ...

6. Chatbot interactions/services queries:
   - When user asks about "services you have provided", "services provided", "queries", "interactions", or "what users asked", they mean chatbot interactions (user queries to the chatbot)
   - Use the `interactions` table (stored in audit database, not hospital database)
   - `interactions` table contains: id, ts_utc, user_id, session_id, role, intent, approved, raw_message, final_message, reply_text, sql_query, row_count, ok, error
   - CRITICAL: When querying interactions table, ALWAYS use SELECT * to include ALL columns, OR explicitly list ALL columns:
     * id, ts_utc, user_id, session_id, role, intent, approved, raw_message, final_message, reply_text, sql_query, row_count, ok, error
   - The `reply_text` column is especially important - it contains the chatbot's full response to the user
   - For "services yesterday": WHERE DATE(ts_utc) = CURRENT_DATE - INTERVAL '1 day' OR WHERE DATE(ts_utc) = CURRENT_DATE - 1
   - For "services today": WHERE DATE(ts_utc) = CURRENT_DATE
   - Complete example: SELECT * FROM interactions WHERE DATE(ts_utc) = CURRENT_DATE - INTERVAL '1 day' ORDER BY ts_utc DESC
   - Or with explicit columns: SELECT id, ts_utc, user_id, session_id, role, intent, approved, raw_message, final_message, reply_text, sql_query, row_count, ok, error FROM interactions WHERE DATE(ts_utc) = CURRENT_DATE - INTERVAL '1 day' ORDER BY ts_utc DESC
   - The `raw_message` column contains the original user query/question
   - The `final_message` column contains the corrected/processed version
   - The `reply_text` column contains the chatbot's full response (THIS IS IMPORTANT - users want to see this!)
   - DO NOT use ap_encounter or ap_encounter_service for chatbot services - use interactions table

7. General SQL best practices:
   - Use proper JOINs (INNER JOIN, LEFT JOIN) instead of comma-separated tables
   - Always qualify column names with table aliases
   - Include is_valid = TRUE filters for data integrity (for hospital tables, not interactions table)
   - Use appropriate WHERE, GROUP BY, ORDER BY, LIMIT clauses
   - Avoid invalid patterns like SELECT col, COUNT(*) FROM ... without GROUP BY
   - PostgreSQL is case-sensitive for identifiers (use lowercase unless quoted)
   - Use schema qualification if needed: schema_name.table_name (default schema is usually 'public')

Allowed operations: {ops}
Database schema (tables and columns from access control):
{schema_str}
{graph_note}
Your goal: generate exactly ONE valid PostgreSQL statement that answers the user's request.
Do NOT add explanations or text; output SQL only.

{nested_rule}

User request: {req_text}
"""
    
    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL output from LLM for PostgreSQL."""
        sql = (sql or "").strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()
        sql = re.sub(
            r"(?i)(here'?s|this is|the following|below is|generated|final|corrected|query is|sql query is|your query).{0,40}:\s*",
            "",
            sql,
        )
        m = re.search(r"\b(select|insert|update|delete)\b", sql, re.IGNORECASE)
        if m:
            sql = sql[m.start():]
        semicolon_idx = sql.find(";")
        if semicolon_idx != -1:
            sql = sql[:semicolon_idx + 1]
        
        # Normalize date functions for PostgreSQL
        # Keep PostgreSQL functions as-is: CURRENT_DATE, NOW(), CURRENT_TIMESTAMP
        # Convert SQLite-style date() to PostgreSQL if present
        sql = re.sub(
            r"date\s*\(\s*'now'\s*,\s*'([+-]?\d+)\s+day'\s*\)",
            lambda m: f"CURRENT_DATE - INTERVAL '{abs(int(m.group(1)))} days'" if m.group(1).startswith('-') else f"CURRENT_DATE + INTERVAL '{m.group(1)} days'",
            sql,
            flags=re.IGNORECASE
        )
        sql = re.sub(
            r"date\s*\(\s*'now'\s*\)",
            "CURRENT_DATE",
            sql,
            flags=re.IGNORECASE
        )
        
        # Convert SQLite boolean checks (is_valid = 1) to PostgreSQL (is_valid = TRUE)
        # Only for known boolean columns
        boolean_columns = ['is_valid', 'is_active', 'is_major', 'is_suspected', 'verified', 'activated', 'discharge']
        for col in boolean_columns:
            # Match: table.col = 1, col = 1
            pattern = rf'\b([a-zA-Z_][a-zA-Z0-9_]*\.)?{col}\s*=\s*1\b'
            replacement = rf'\1{col} = TRUE'
            sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)
            
            pattern = rf'\b([a-zA-Z_][a-zA-Z0-9_]*\.)?{col}\s*=\s*0\b'
            replacement = rf'\1{col} = FALSE'
            sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)
        
        # Fix malformed subqueries in WHERE clauses (common LLM mistake)
        # WHERE col = (SELECT wrong_col, MAX(...) FROM ...) -> WHERE col = (SELECT MAX(...) FROM ...)
        sql = re.sub(
            r"(WHERE\s+[^=]+=\s*\(SELECT\s+)([^,]+),\s*(MAX|MIN|COUNT|SUM|AVG)",
            r"\1\3",
            sql,
            flags=re.IGNORECASE
        )
        
        # Simplify date comparisons for PostgreSQL
        # Convert complex subqueries to simple date arithmetic
        sql = re.sub(
            r"WHERE\s+(\w+\.\w+)\s*=\s*\(SELECT\s+[^)]*MAX\([^)]+\)\s+FROM\s+[^)]*WHERE\s+[^<]*<\s*CURRENT_DATE\)",
            lambda m: f"WHERE {m.group(1)} = CURRENT_DATE - INTERVAL '1 day'",
            sql,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # CRITICAL: Convert discharge_at IS NULL to discharge_at = 0 for PostgreSQL
        # In this database, non-discharged patients have discharge_at = 0, not NULL
        # This is especially important for "admitted patients" queries
        sql = re.sub(
            r'\b(\w+\.)?discharge_at\s+IS\s+NULL\b',
            r'\1discharge_at = 0',
            sql,
            flags=re.IGNORECASE
        )
        
        # Also handle NOT NULL cases
        sql = re.sub(
            r'\b(\w+\.)?discharge_at\s+IS\s+NOT\s+NULL\b',
            r'\1discharge_at != 0',
            sql,
            flags=re.IGNORECASE
        )
        
        sql = re.split(r"(?i)\bnote that\b", sql)[0]
        return sql.strip()
    
    def _starts_with_valid_op(self, sql: str) -> bool:
        """Check if SQL starts with valid operation."""
        s = (sql or "").lstrip().lower()
        return s.startswith(("select", "insert", "update", "delete"))
    


# Global instance
_sql_generation_service = SQLGenerationService()

