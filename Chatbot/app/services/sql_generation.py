"""SQL generation service - encapsulates SQL generation logic."""
import re
import logging
from typing import Dict, Any, Set, Optional, List
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
        user_access = self.access_control_repo.get_user_access(user_id)
        if not user_access:
            raise ValueError(f"User {user_id} not in access_control.json")

        allowed_schema = user_access.get("allowed_schema") or {}
        allowed_tables = set(allowed_schema.keys())

        # Cached schema_graph.json can be stale relative to access_control.json.
        # Ensure graph covers all allowed tables so table detection and prompts stay consistent.
        if self._ensure_graph_covers_allowed_schema(allowed_schema):
            self.field_index = self._build_field_index(self.schema_graph)

        # ChatOrchestrator may pass an "enhanced" prompt (e.g., "User said: ... Entities: ...").
        # Use only the user's actual question for table detection to avoid schema explosion.
        table_detection_text = self._extract_user_text_for_table_detection(text)

        # Deterministic templates for common, high-signal intents (avoids LLM column hallucinations)
        template_sql = self._try_generate_template_sql(table_detection_text, allowed_schema)
        if template_sql:
            logger.info("🧩 Using deterministic SQL template for request")
            return template_sql
        
        # Detect relevant tables from user query
        initial_tables = self._detect_relevant_tables_from_text(table_detection_text, allowed_tables)
        
        # If no tables detected, use intelligent fallback based on common keywords
        if not initial_tables:
            initial_tables = self._fallback_table_detection(table_detection_text, allowed_schema)
        
        # Expand via graph (but limit expansion to prevent explosion)
        expanded_tables = self._expand_tables_by_graph(initial_tables)
        
        # Limit total tables to prevent huge prompts (max 20 tables)
        if len(expanded_tables) > 20:
            before = len(expanded_tables)
            # Keep initial tables + most connected tables
            expanded_tables = self._limit_tables_intelligently(initial_tables, expanded_tables, max_tables=20)
            after = len(expanded_tables)
            logger.warning(f"⚠️ Too many tables detected ({before}); reduced to {after} tables (target ≤ 20)")
            if after > 20:
                logger.warning(
                    f"⚠️ Could not reduce to ≤ 20 tables (initial={len(initial_tables)}, expanded={after}). "
                    "Consider tightening table detection heuristics."
                )
        
        reduced_graph = self._restrict_schema_context(expanded_tables, allowed_tables)
        
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

    def _extract_user_text_for_table_detection(self, text: str) -> str:
        """
        Extract the user's actual question from an orchestrator-enhanced prompt.

        Expected formats (examples):
          - "User said: <question>. Entities (...): ..."
          - "User said: <question>\\nEntities: ..."
        """
        if not text:
            return ""

        m = re.search(
            r"(?is)\buser\s+said\s*:\s*(?P<q>.*?)(?:\.\s*entities\b|\n\s*entities\b|$)",
            text,
        )
        if m:
            q = (m.group("q") or "").strip()
            return q or text

        return text

    def _ensure_graph_covers_allowed_schema(self, allowed_schema: Dict[str, Any]) -> bool:
        """
        Ensure `self.schema_graph` contains at least the tables present in access control.

        This prevents stale cached graphs from hiding newly-added tables (e.g. `patient_encounters`),
        which would otherwise cause the LLM prompt to omit them.

        Returns True if the graph was modified.
        """
        if not isinstance(allowed_schema, dict) or not allowed_schema:
            return False

        modified = False
        for table, details in allowed_schema.items():
            if table in self.schema_graph:
                continue
            cols = []
            if isinstance(details, dict):
                cols = details.get("columns", []) or []
            self.schema_graph[table] = {"columns": list(cols), "foreign_keys": []}
            modified = True

        return modified
    
    def _detect_relevant_tables_from_text(self, text: str, allowed_tables: Set[str]) -> Set[str]:
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

        # If the user mentions an MRN/record identifier, ensure patient tables are present in the schema context.
        # This matters even for lab/diagnostic queries, since MRN filtering typically happens via `patients`.
        if any(
            term in text_lower
            for term in [
                "mrn",
                "medical record",
                "medical number",
                "record number",
                "record id",
                "record identifier",
            ]
        ):
            if "patients" in self.schema_graph and "patients" in allowed_tables:
                tables.add("patients")

        # Labs/diagnostics: keep initial tables small and high-signal to avoid schema explosion.
        # (Graph expansion will bring in related tables if foreign keys exist.)
        is_labish = bool(re.search(r"\b(lab|labs|laboratory|diagnostic)\b", text_lower)) or (
            ("result" in text_lower or "results" in text_lower) and ("test" in text_lower or "tests" in text_lower)
        )
        if is_labish:
            for t in [
                "patients",
                "ap_diagnostic_orders",
                "ap_diagnostic_order_tests",
                "ap_diagnostic_order_tests_result",
                "ap_diagnostic_test",
                "ap_catalog_diagnostic_test",
                "ap_lov_values",
            ]:
                if t in self.schema_graph and t in allowed_tables:
                    tables.add(t)
        
        # Method 1: Field-based detection (existing)
        for tok in tokens:
            if tok in self.field_index:
                tables.update({t for t in self.field_index[tok] if t in allowed_tables})
        
        # Method 2: Direct table name matching (e.g., "patient", "encounter", "diagnosis")
        # Map common keywords to table prefixes
        keyword_to_prefixes: Dict[str, List[str]] = {
            "patient": ["patients", "patient"],
            "encounter": ["patient_encounters", "ap_encounter"],
            "appointment": ["patient_encounters", "ap_encounter", "ap_appointment"],
            "visit": ["patient_encounters", "ap_encounter"],
            "admission": ["patient_encounters", "ap_encounter"],
            "diagnosis": ["ap_patient_diagnose"],
            "diagnose": ["ap_patient_diagnose"],
            "allergy": ["ap_patient_allergies"],
            "allergies": ["ap_patient_allergies"],
            "medication": ["ap_prescription_medications"],
            "medications": ["ap_prescription_medications"],
            "prescription": ["ap_prescription"],
            "drug": ["ap_drug_order"],
            "observation": ["ap_patient_observation"],
            "vital": ["ap_patient_observation"],
            "insurance": ["ap_patient_insurance"],
            "problem": ["ap_patient_problem"],
            "chronic": ["ap_patient_problem"],
        }

        for keyword, prefixes in keyword_to_prefixes.items():
            if keyword in text_lower:
                for table_prefix in prefixes:
                    for table_name in self.schema_graph.keys():
                        if table_name.startswith(table_prefix):
                            if table_name in allowed_tables:
                                tables.add(table_name)
        
        return tables
    
    def _fallback_table_detection(self, text: str, allowed_schema: Dict[str, Any]) -> Set[str]:
        """Intelligent fallback when no tables detected - use common patient-related tables."""
        text_lower = text.lower()
        fallback_tables = set()
        
        # Always include core patient table
        if "patients" in allowed_schema:
            fallback_tables.add("patients")
        elif "patient" in allowed_schema:
            fallback_tables.add("patient")
        elif "ap_patient" in allowed_schema:
            fallback_tables.add("ap_patient")
        
        # Add encounter if query mentions time/date/admission/discharge
        if any(word in text_lower for word in ['admission', 'discharge', 'encounter', 'visit', 'admitted', 'discharged', 'date', 'recent', 'last']):
            if "patient_encounters" in allowed_schema:
                fallback_tables.add("patient_encounters")
            elif "ap_encounter" in allowed_schema:
                fallback_tables.add("ap_encounter")
        
        # Add diagnosis if query mentions diagnosis/condition
        if any(word in text_lower for word in ['diagnosis', 'diagnose', 'condition', 'disease', 'illness']):
            if "ap_patient_diagnose" in allowed_schema:
                fallback_tables.add("ap_patient_diagnose")
        
        # If still empty, return just patient table (minimal fallback)
        if not fallback_tables:
            if "patients" in allowed_schema:
                fallback_tables.add("patients")
            elif "patient" in allowed_schema:
                fallback_tables.add("patient")
            elif "ap_patient" in allowed_schema:
                fallback_tables.add("ap_patient")
        
        return fallback_tables
    
    def _limit_tables_intelligently(self, initial_tables: Set[str], expanded_tables: Set[str], max_tables: int = 20) -> Set[str]:
        """Limit tables intelligently by keeping initial + most connected tables."""
        if len(expanded_tables) <= max_tables:
            return expanded_tables
        
        # Always keep initial tables
        result = set(initial_tables)

        # If initial selection already exceeds max, trim it down by connectivity.
        if len(result) > max_tables:
            always_keep = [t for t in ["patients", "patient", "patient_encounters", "ap_diagnostic_orders", "ap_encounter"] if t in result]
            candidates = [t for t in result if t not in always_keep]

            def _score(table: str) -> int:
                score = 0
                info = self.schema_graph.get(table) or {}
                score += len(info.get("foreign_keys", []) or [])
                for other, oinfo in self.schema_graph.items():
                    for fk in oinfo.get("foreign_keys", []) or []:
                        if fk.get("to_table") == table:
                            score += 1
                return score

            candidates_sorted = sorted(candidates, key=_score, reverse=True)
            kept = set(always_keep + candidates_sorted[: max(0, max_tables - len(always_keep))])
            result = kept
        
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
    
    def _restrict_schema_context(self, tables: Set[str], allowed_tables: Set[str]) -> Dict[str, Dict[str, Any]]:
        """Return reduced schema graph restricted to tables allowed by access control."""
        allowed = allowed_tables or set()
        return {
            t: self.schema_graph[t]
            for t in tables
            if t in self.schema_graph and (not allowed or t in allowed)
        }
    
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
- Prefer the `patients` table for patient demographics and patient-detail questions
- For appointments/visits/encounters, prefer `patient_encounters` when present (do not use `ap_patient`)
- For ICD diagnosis lookups, `icd_diagnosis` uses `icd_short_description` / `icd_full_description` (do not use a `description` column unless the schema explicitly lists it)
- Always use table aliases (e.g., FROM patients p) and qualify column names (e.g., p.id, p.first_name)
- For legacy `ap_*` tables, the primary key is usually `key` (NOT `id`). Do not reference `*.id` unless the schema explicitly lists an `id` column.
- Always include is_valid = TRUE filters when querying legacy `ap_*` tables
- Use double quotes for identifiers only if needed (usually lowercase identifiers work without quotes)
- Use single quotes for string literals
- Legacy `ap_*`.key and *_patient_key fields are often TEXT identifiers, even when they look numeric. Compare them as quoted strings, e.g. e.patient_key = '220571659221387'
- TIMESTAMP CONVERSION: Admission date is e.created_at (millisecond timestamp), discharge date is e.discharge_at (millisecond timestamp)
  - To convert millisecond timestamp to date: TO_TIMESTAMP(e.created_at / 1000.0) for PostgreSQL
  - To compare with dates: TO_TIMESTAMP(e.created_at / 1000.0) >= CURRENT_DATE - INTERVAL '7 days'
  - For display: Use TO_CHAR(TO_TIMESTAMP(e.created_at / 1000.0), 'YYYY-MM-DD') AS admission_date

QUERY INTERPRETATION GUIDELINES:
1. "Recently" or "recent": 
   - Use ORDER BY date_column DESC LIMIT N (N=5-10) for most recent records
   - OR use date_column >= CURRENT_DATE - INTERVAL '90 days' for time-based filters (90 days is reasonable for "recently")
   - DO NOT use strict 7-day filters for "recently" - use 90 days or ORDER BY with LIMIT

2. "Last 2 weeks" or "past 2 weeks":
   - Only apply a 14-day filter when the user explicitly asks for that date range
   - Filter by admission date: TO_TIMESTAMP(e.created_at / 1000.0) >= CURRENT_DATE - INTERVAL '14 days'
   - Prefer filtering encounter/appointment tables instead of querying deprecated patient tables directly
   - Example: SELECT p.medical_record_number AS medical_record_number, TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')) AS full_name FROM patients p WHERE p.medical_record_number IS NOT NULL ORDER BY p.medical_record_number DESC

3. "Last" or "most recent": 
   - Use ORDER BY date_column DESC LIMIT 1
   - No date filter needed, just order and limit

3. "Are all X Y?" questions:
   - This means "check if every X has property Y"
   - Use: SELECT COUNT(*) FROM table WHERE condition IS NULL (to find ones that don't have the property)
   - Or: SELECT COUNT(*) FROM table1 WHERE NOT EXISTS (SELECT 1 FROM table2 WHERE ...)
   - DO NOT use: SELECT COUNT(*) = (SELECT COUNT(*) ...) in SELECT clause
   - Example for "are all discharged": SELECT COUNT(*) AS not_discharged FROM ap_encounter e WHERE e.is_valid = TRUE AND e.discharge_at = 0
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
   - Primary criteria: e.discharge_at = 0 AND e.is_valid = TRUE
    - Example: SELECT ap.patient_mrn AS medical_record_number, e.patient_full_name AS patient_name, TO_CHAR(TO_TIMESTAMP(e.created_at / 1000.0), 'YYYY-MM-DD') AS admission_date FROM ap_encounter e JOIN ap_patient ap ON ap.key = e.patient_key AND ap.is_valid = TRUE WHERE e.discharge_at = 0 AND e.is_valid = TRUE ORDER BY e.created_at DESC LIMIT 1
   - For "last admitted": Add ORDER BY e.created_at DESC LIMIT 1
   - To convert millisecond timestamp to date: Use TO_TIMESTAMP(e.created_at / 1000.0) for PostgreSQL

 5. Patient identifier requirement:
    - When querying the `patients` table, ALWAYS include p.medical_record_number AS medical_record_number in the SELECT clause
    - This enables the frontend to create clickable patient detail links
    - Use table alias 'p' for the main patient table
    - `patients.id` is numeric. If the user gives an alphanumeric record identifier such as P100, MRN-77, or says "record", "mrn", or "medical number", use `p.medical_record_number`, not `p.id`
    - Example: SELECT p.medical_record_number AS medical_record_number, p.first_name, p.last_name FROM patients p ...

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

    def _try_generate_template_sql(self, text: str, allowed_schema: Dict[str, Any]) -> Optional[str]:
        """
        Try to generate SQL without the LLM for a few common high-signal requests.

        Returns a SQL string (ending with ';') or None to fall back to the LLM.
        """
        text_lower = (text or "").lower()

        # Recent appointments / encounters (prefer modern tables when present)
        is_recentish = bool(re.search(r"\b(recent|latest|last|most\s+recent)\b", text_lower))
        is_appointmentish = bool(re.search(r"\b(appointment|appointments|encounter|encounters|visit|visits)\b", text_lower))
        if is_recentish and is_appointmentish:
            if "patient_encounters" in allowed_schema:
                joins: List[str] = []

                # patient_encounters.patient_id does not always match patients.id in some deployments.
                # Use LEFT JOIN to avoid filtering out encounters when patient demographic records are missing/mismatched.
                patient_name_expr = "''::TEXT AS patient_name"
                patient_mrn_expr = "''::TEXT AS medical_record_number"
                if "patients" in allowed_schema:
                    joins.append("LEFT JOIN patients p ON p.id = pe.patient_id")
                    patient_name_expr = (
                        "TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.second_name, '') || ' ' || "
                        "COALESCE(p.third_name, '') || ' ' || COALESCE(p.last_name, '')) AS patient_name"
                    )
                    patient_mrn_expr = "p.medical_record_number AS medical_record_number"

                practitioner_name_expr = "''::TEXT AS practitioner_name"
                if "practitioner" in allowed_schema:
                    joins.append("LEFT JOIN practitioner pr ON pr.id = pe.practitioner_id")
                    practitioner_name_expr = (
                        "TRIM(COALESCE(pr.first_name, '') || ' ' || COALESCE(pr.last_name, '')) AS practitioner_name"
                    )

                return f"""
 SELECT
   pe.id AS encounter_id,
   {patient_mrn_expr},
   {patient_name_expr},
   pe.encounter_number,
   pe.status,
   pe.encounter_date,
   {practitioner_name_expr}
 FROM patient_encounters pe
 {' '.join(joins)}
 ORDER BY pe.encounter_date DESC
 LIMIT 10;
 """.strip()

            if "ap_encounter" in allowed_schema and "ap_patient" in allowed_schema:
                return """
SELECT
  e.key AS encounter_id,
  ap.patient_mrn AS medical_record_number,
  e.patient_full_name AS patient_name,
  TO_CHAR(TO_TIMESTAMP(e.created_at / 1000.0), 'YYYY-MM-DD') AS admission_date
FROM ap_encounter e
JOIN ap_patient ap
  ON ap.key = e.patient_key
  AND ap.is_valid = TRUE
WHERE e.is_valid = TRUE
ORDER BY e.created_at DESC
LIMIT 10;
""".strip()

            if "ap_encounter" in allowed_schema:
                return """
SELECT
  e.key AS encounter_id,
  ''::TEXT AS medical_record_number,
  e.patient_full_name AS patient_name,
  TO_CHAR(TO_TIMESTAMP(e.created_at / 1000.0), 'YYYY-MM-DD') AS admission_date
FROM ap_encounter e
WHERE e.is_valid = TRUE
ORDER BY e.created_at DESC
LIMIT 10;
""".strip()

        # Patients with unknown/missing names
        if (
            "patients" in allowed_schema
            and re.search(r"\bpatient|patients\b", text_lower)
            and re.search(r"\bunknown\b", text_lower)
            and re.search(r"\bname|names\b", text_lower)
        ):
            return """
SELECT
  p.medical_record_number,
  TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.second_name, '') || ' ' || COALESCE(p.third_name, '') || ' ' || COALESCE(p.last_name, '')) AS patient_name,
  p.first_name,
  p.last_name,
  p.is_unknown
FROM patients p
WHERE
  p.is_unknown = TRUE
  OR TRIM(COALESCE(p.first_name, '') || COALESCE(p.second_name, '') || COALESCE(p.third_name, '') || COALESCE(p.last_name, '')) = ''
  OR LOWER(COALESCE(p.first_name, '')) IN ('unknown', 'unk', 'n/a', 'na')
  OR LOWER(COALESCE(p.last_name, '')) IN ('unknown', 'unk', 'n/a', 'na')
  OR (COALESCE(p.first_name, '') || ' ' || COALESCE(p.second_name, '') || ' ' || COALESCE(p.third_name, '') || ' ' || COALESCE(p.last_name, '')) ILIKE '%unknown%'
ORDER BY p.id
LIMIT 200;
""".strip()

        # Cohort: patients filtered by gender + blood type/group (legacy schema)
        # Commonly requested as "list all females with blood type O" (typos happen in correction stage).
        has_blood = "blood" in text_lower and any(tok in text_lower for tok in ["type", "ttype", "tyype", "group"])
        has_gender = any(tok in text_lower for tok in ["female", "females", "male", "males", "women", "woman", "men", "man"])
        if has_blood and has_gender and ("ap_patient" in allowed_schema):
            # Use word-boundary matches so "female" doesn't trigger "male".
            want_female = bool(re.search(r"\b(female|females|woman|women)\b", text_lower))
            want_male = bool(re.search(r"\b(male|males|man|men)\b", text_lower))

            # Extract a simple ABO token if present; otherwise default to any group.
            # Accept both letter O and zero 0 as "O".
            abo = ""
            m = re.search(r"\b(?:blood\s+(?:type|ttype|tyype|group)\s*)?([ab]|ab|o|0)\b", text_lower)
            if m:
                abo = (m.group(1) or "").strip().upper()
                if abo == "0":
                    abo = "O"

            has_lov = "ap_lov_values" in allowed_schema
            joins = ""
            gender_select = "CAST(ap.gender_lkey AS TEXT) AS gender"
            blood_select = "CAST(ap.blood_group_lkey AS TEXT) AS blood_type"
            if has_lov:
                joins = """
LEFT JOIN ap_lov_values g
  ON g.key = ap.gender_lkey
  AND g.is_valid = TRUE
LEFT JOIN ap_lov_values b
  ON b.key = ap.blood_group_lkey
  AND b.is_valid = TRUE
""".rstrip()
                gender_select = "COALESCE(CAST(g.lov_display_vale AS TEXT), CAST(ap.gender_lkey AS TEXT)) AS gender"
                blood_select = "COALESCE(CAST(b.lov_display_vale AS TEXT), CAST(ap.blood_group_lkey AS TEXT)) AS blood_type"

            gender_filter = ""
            if want_female and not want_male:
                if has_lov:
                    gender_filter = (
                        "AND (\n"
                        "  LOWER(COALESCE(CAST(ap.gender_lkey AS TEXT), '')) LIKE 'female%'\n"
                        "  OR LOWER(COALESCE(CAST(g.lov_display_vale AS TEXT), '')) LIKE 'female%'\n"
                        ")\n"
                    )
                else:
                    gender_filter = "AND LOWER(COALESCE(CAST(ap.gender_lkey AS TEXT), '')) LIKE 'female%'\n"
            elif want_male and not want_female:
                if has_lov:
                    gender_filter = (
                        "AND (\n"
                        "  LOWER(COALESCE(CAST(ap.gender_lkey AS TEXT), '')) LIKE 'male%'\n"
                        "  OR LOWER(COALESCE(CAST(g.lov_display_vale AS TEXT), '')) LIKE 'male%'\n"
                        ")\n"
                    )
                else:
                    gender_filter = "AND LOWER(COALESCE(CAST(ap.gender_lkey AS TEXT), '')) LIKE 'male%'\n"

            blood_filter = ""
            if abo:
                # Allow O+, O-, etc by prefix match.
                if has_lov:
                    blood_filter = (
                        "AND (\n"
                        f"  LOWER(COALESCE(CAST(ap.blood_group_lkey AS TEXT), '')) LIKE '{abo.lower()}%'\n"
                        f"  OR LOWER(COALESCE(CAST(b.value_code AS TEXT), '')) LIKE '{abo.lower()}%'\n"
                        f"  OR LOWER(COALESCE(CAST(b.lov_display_vale AS TEXT), '')) LIKE '{abo.lower()}%'\n"
                        ")\n"
                    )
                else:
                    blood_filter = f"AND LOWER(COALESCE(CAST(ap.blood_group_lkey AS TEXT), '')) LIKE '{abo.lower()}%'\n"

            return f"""
SELECT
  ap.key AS patient_key,
  ap.patient_mrn,
  ap.full_name,
  {gender_select},
  {blood_select}
FROM ap_patient ap
{joins}
WHERE ap.is_valid = TRUE
{gender_filter}{blood_filter}ORDER BY ap.key
LIMIT 1000;
""".strip()

        # Patients with a given primary diagnosis (avoid LLM column hallucinations)
        is_primary_dx_query = bool(re.search(r"\bprimary\s+diagnos", text_lower))
        is_dx_query = bool(re.search(r"\bdiagnos", text_lower))
        if is_primary_dx_query and is_dx_query:
            term = ""
            m = re.search(
                r"\bwith\s+(?P<t>.+?)\s+(?:as\s+)?primary\s+diagnos",
                text_lower,
            )
            if m:
                term = (m.group("t") or "").strip()
            if not term:
                m = re.search(r"\bprimary\s+diagnos(?:is)?\s+of\s+(?P<t>.+?)\b", text_lower)
                if m:
                    term = (m.group("t") or "").strip()

            term = re.sub(r"[^a-z0-9 _/-]+", " ", term).strip()
            term = re.sub(r"\s+", " ", term)
            if term:
                like = "%" + term.replace("'", "''") + "%"

                # Prefer legacy encounter/diagnosis tables when modern `patient_diagnoses` is empty in many deployments.
                if {"ap_patient_diagnose", "ap_encounter", "ap_lov_values", "ap_patient"}.issubset(set(allowed_schema.keys())):
                    return f"""
 SELECT DISTINCT
  ap.patient_mrn AS medical_record_number,
  e.patient_full_name AS patient_name,
  COALESCE(c.icd_code, d.diagnose_code) AS diagnose_code,
  COALESCE(c.description, c.fulldescription, d.description) AS diagnosis_description,
  e.key AS encounter_id,
  COALESCE(d.date_diagnosed, TO_TIMESTAMP(d.created_at / 1000.0)::DATE) AS diagnosed_date
 FROM ap_patient_diagnose d
 JOIN ap_encounter e
   ON e.key = d.visit_key
   AND e.is_valid = TRUE
 JOIN ap_patient ap
   ON ap.key = e.patient_key
   AND ap.is_valid = TRUE
 LEFT JOIN ap_icd_code c
   ON c.key = d.diagnose_code
 JOIN ap_lov_values dt
   ON dt.key = d.diagnose_type_lkey
  AND dt.is_valid = TRUE
  AND dt.lov_code = 'DIAGNOSIS_TYPE'
  AND dt.value_code = 'DIAG_TYP_PRIMARY'
WHERE d.is_valid = TRUE
  AND COALESCE(d.is_suspected, FALSE) = FALSE
  AND (
    COALESCE(c.fulldescription, c.description, d.description, '') ILIKE '{like}'
    OR COALESCE(c.icd_code, '') ILIKE '{like}'
    OR COALESCE(d.diagnose_code, '') ILIKE '{like}'
  )
ORDER BY diagnosed_date DESC NULLS LAST
LIMIT 100;
""".strip()

                if {"patients", "patient_diagnoses", "icd_diagnosis"}.issubset(set(allowed_schema.keys())):
                    return f"""
 SELECT DISTINCT
  p.medical_record_number,
  TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.second_name, '') || ' ' || COALESCE(p.third_name, '') || ' ' || COALESCE(p.last_name, '')) AS patient_name,
  d.icd_code,
  d.icd_short_description,
  d.icd_full_description
FROM patients p
JOIN patient_diagnoses pd
  ON pd.patient_id = p.id
JOIN icd_diagnosis d
  ON d.id = pd.diagnosis_id
WHERE LOWER(pd.type) = 'primary'
  AND (
    d.icd_short_description ILIKE '{like}'
    OR d.icd_full_description ILIKE '{like}'
    OR CAST(d.icd_code AS TEXT) ILIKE '{like}'
  )
ORDER BY p.id
LIMIT 100;
""".strip()

        # Lab results/requests for a specific MRN
        # Bridge modern `patients` (MRN in medical_record_number) to legacy `ap_*` diagnostic tables via `ap_patient.patient_mrn`,
        # which corresponds to the numeric `patients.id` in this dataset.
        is_lab_query = bool(re.search(r"\b(lab|labs|laboratory)\b", text_lower))
        is_request_query = bool(re.search(r"\b(request|order|orders|requested)\b", text_lower))
        is_result_query = bool(re.search(r"\b(result|results)\b", text_lower))
        mrn_match = re.search(r"\bmrn\s*([a-zA-Z0-9_-]+)\b", text or "", re.IGNORECASE)
        if mrn_match and is_lab_query and (is_request_query or is_result_query):
            mrn = mrn_match.group(1)
            required = {"patients", "ap_diagnostic_orders", "ap_diagnostic_order_tests_result"}
            if not required.issubset(set(allowed_schema.keys())):
                return None

            # Prefer joining orders directly to `patients` when modern encounter tables exist.
            # Fall back to the legacy bridge via `ap_patient` when needed.
            use_legacy_bridge = "ap_patient" in allowed_schema and "patient_encounters" not in allowed_schema
            if use_legacy_bridge:
                return f"""
SELECT
  p.medical_record_number,
  o.key AS diagnostic_order_key,
  CAST(o.lab_status_lkey AS TEXT) AS lab_status,
  TO_CHAR(TO_TIMESTAMP(o.created_at / 1000.0), 'YYYY-MM-DD HH24:MI') AS order_created_at,
  r.key AS result_key,
  r.result_value_number,
  r.result_text,
  TO_CHAR(TO_TIMESTAMP(r.created_at / 1000.0), 'YYYY-MM-DD HH24:MI') AS result_created_at
FROM patients p
JOIN ap_patient ap
  ON CAST(ap.patient_mrn AS TEXT) = CAST(p.id AS TEXT)
  AND ap.is_valid = TRUE
LEFT JOIN ap_diagnostic_orders o
  ON o.patient_key = ap.key
  AND o.is_valid = TRUE
LEFT JOIN ap_diagnostic_order_tests_result r
  ON r.order_key = o.key
  AND r.is_valid = TRUE
WHERE CAST(p.medical_record_number AS TEXT) = '{mrn}'
ORDER BY COALESCE(r.created_at, o.created_at) DESC NULLS LAST
LIMIT 100;
""".strip()

            return f"""
SELECT
  p.medical_record_number,
  o.key AS diagnostic_order_key,
  CAST(o.lab_status_lkey AS TEXT) AS lab_status,
  TO_CHAR(TO_TIMESTAMP(o.created_at / 1000.0), 'YYYY-MM-DD HH24:MI') AS order_created_at,
  r.key AS result_key,
  r.result_value_number,
  r.result_text,
  TO_CHAR(TO_TIMESTAMP(r.created_at / 1000.0), 'YYYY-MM-DD HH24:MI') AS result_created_at
FROM patients p
LEFT JOIN ap_diagnostic_orders o
  ON CAST(o.patient_key AS TEXT) = CAST(p.id AS TEXT)
  AND o.is_valid = TRUE
LEFT JOIN ap_diagnostic_order_tests_result r
  ON r.order_key = o.key
  AND r.is_valid = TRUE
WHERE CAST(p.medical_record_number AS TEXT) = '{mrn}'
ORDER BY COALESCE(r.created_at, o.created_at) DESC NULLS LAST
LIMIT 100;
""".strip()

        # Pending lab requests / orders across patients
        # Use ap_diagnostic_orders.lab_status_lkey joined to ap_lov_values (LAB_TESTS_STATUS) when available.
        is_request_query = bool(re.search(r"\b(request|order|orders)\b", text_lower))
        is_pending_query = bool(re.search(r"\b(pending|outstanding|open|awaiting|not\s+done|unresolved)\b", text_lower))
        if is_lab_query and (is_request_query or is_pending_query):
            required = {"ap_diagnostic_orders", "ap_lov_values"}
            if not required.issubset(set(allowed_schema.keys())):
                return None

            has_patient = "patients" in allowed_schema or "ap_patient" in allowed_schema
            has_encounter = "ap_encounter" in allowed_schema

            patient_join = ""
            patient_cols = "''::TEXT AS medical_record_number"
            patient_filters = ""
            if "patients" in allowed_schema:
                patient_join = "JOIN patients p ON CAST(p.id AS TEXT) = CAST(o.patient_key AS TEXT)"
                patient_cols = (
                    "p.medical_record_number AS medical_record_number, "
                    "TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.second_name, '') || ' ' || "
                    "COALESCE(p.third_name, '') || ' ' || COALESCE(p.last_name, '')) AS patient_name"
                )
            elif has_patient and "patient_encounters" not in allowed_schema:
                patient_join = "JOIN ap_patient p ON p.key = o.patient_key"
                patient_cols = "p.patient_mrn AS medical_record_number, p.full_name AS patient_name"
                patient_filters = "AND p.is_valid = TRUE"

            encounter_join = ""
            encounter_cols = "o.visit_key AS encounter_id"
            if has_encounter:
                # Keep encounter filtering in the JOIN so we don't accidentally drop lab orders
                # that have missing/invalid encounter linkage.
                encounter_join = (
                    "LEFT JOIN ap_encounter e ON e.key = o.visit_key "
                    "AND e.is_valid = TRUE AND COALESCE(e.discharge_at, 0) = 0"
                )
                encounter_cols = "e.key AS encounter_id"

            # "Pending" lab statuses in this dataset:
            # - LAB_TEST_NEW, LAB_TEST_ACCEPTED, ORDER_PARTIAL
            # Exclude final statuses like LAB_TEST_APPROVED ("Result Approved").
            return f"""
SELECT
  o.key AS diagnostic_order_key,
  {patient_cols},
  {encounter_cols},
  lv.lov_display_vale AS lab_status,
  TO_CHAR(TO_TIMESTAMP(o.created_at / 1000.0), 'YYYY-MM-DD HH24:MI') AS created_at
FROM ap_diagnostic_orders o
LEFT JOIN ap_lov_values lv
  ON lv.key = o.lab_status_lkey
  AND lv.is_valid = TRUE
{patient_join}
{encounter_join}
WHERE o.is_valid = TRUE
  {patient_filters}
  AND (lv.value_code IN ('LAB_TEST_NEW', 'LAB_TEST_ACCEPTED', 'ORDER_PARTIAL') OR lv.value_code IS NULL)
ORDER BY o.created_at DESC
LIMIT 50;
""".strip()

        return None
    
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

        # Patient keys are stored as text, so numeric-looking identifiers must be quoted.
        sql = re.sub(
            r"\b((?:[a-zA-Z_][a-zA-Z0-9_]*\.)?(?:key|patient_key))\s*=\s*(\d{6,})\b",
            r"\1 = '\2'",
            sql,
            flags=re.IGNORECASE,
        )

        if re.search(r"\bfrom\s+patients\b", sql, re.IGNORECASE):
            sql = re.sub(
                r"\b((?:[a-zA-Z_][a-zA-Z0-9_]*\.)?)id\s*=\s*'([A-Za-z][A-Za-z0-9_-]*)'",
                r"\1medical_record_number = '\2'",
                sql,
                flags=re.IGNORECASE,
            )
            sql = re.sub(
                r"CAST\(\s*((?:[a-zA-Z_][a-zA-Z0-9_]*\.)?)id\s+AS\s+TEXT\s*\)\s*=\s*'([A-Za-z][A-Za-z0-9_-]*)'",
                r"CAST(\1medical_record_number AS TEXT) = '\2'",
                sql,
                flags=re.IGNORECASE,
            )

        # Safety/performance guard: if the LLM emits a SELECT without WHERE or LIMIT,
        # add a conservative LIMIT so it passes business rules and avoids full scans.
        sql_lower = sql.lstrip().lower()
        has_where = re.search(r"\bwhere\b", sql_lower) is not None
        has_limit = re.search(r"\blimit\b", sql_lower) is not None
        if sql_lower.startswith("select") and not has_where and not has_limit:
            has_semicolon = sql.rstrip().endswith(";")
            if has_semicolon:
                sql = sql.rstrip()[:-1].rstrip()
            sql = f"{sql} LIMIT 200"
            if has_semicolon:
                sql = f"{sql};"
        
        sql = re.split(r"(?i)\bnote that\b", sql)[0]
        return sql.strip()
    
    def _starts_with_valid_op(self, sql: str) -> bool:
        """Check if SQL starts with valid operation."""
        s = (sql or "").lstrip().lower()
        return s.startswith(("select", "insert", "update", "delete"))
    


# Global instance
_sql_generation_service = SQLGenerationService()
