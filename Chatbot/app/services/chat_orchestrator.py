"""Chat orchestrator service - main business logic for chat pipeline."""
import json
import time
import logging
import sys
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Any
from app.services.session_memory import SessionMemoryService
from app.services.intent import IntentDetectionService
from app.services.correction import SpellingCorrectionService
from app.services.scope import ScopeDetectionService
from app.services.entities import EntityExtractionService
from app.services.patient_details import PatientDetailsService
from app.services.rules import BusinessRulesService, get_rules_service
from app.infrastructure.db.audit_repo import AuditRepository
from app.infrastructure.db.hospital_repo import HospitalRepository
from app.infrastructure.config.access_control_repo import AccessControlRepository
from app.infrastructure.http.clients import post_json_logged
from app.infrastructure.llm.llm_client import get_llm_client
from app.core.config import settings
from app.services.entities import SYSTEM_PROMPT
from app.services.advice import ClinicianAdviceService, is_advice_style_question
from app.services.statistics import StatisticsService

logger = logging.getLogger(__name__)
# Ensure logger propagates to root logger (which has file handler)
logger.setLevel(logging.INFO)
logger.propagate = True  # Allow logs to propagate to root logger
# Don't add separate handlers - use root logger's handlers


class ChatOrchestratorService:
    """Main orchestrator service for chat pipeline."""

    def _is_patient_id_field(self, key: str) -> bool:
        lk = str(key or "").lower()
        return lk == "patientid" or lk == "patients_id" or "patient_id" in lk

    def _strip_patient_id_fields_from_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return rows
        out: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append({k: v for k, v in row.items() if not self._is_patient_id_field(k)})
        return out

    def _strip_patient_id_fields_from_columns(self, columns: List[str]) -> List[str]:
        if not columns:
            return columns
        return [c for c in columns if not self._is_patient_id_field(c)]

    def _extract_unique_mrns_from_rows(self, rows: List[Dict[str, Any]]) -> List[str]:
        if not rows or not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return []

        def is_mrn_field(key: str) -> bool:
            lk = str(key or "").lower()
            return (
                lk == "mrn"
                or "medical_record_number" in lk
                or "patient_mrn" in lk
                or lk.endswith("_mrn")
            )

        mrn_cols = [k for k in rows[0].keys() if is_mrn_field(k)]
        if not mrn_cols:
            return []

        col = mrn_cols[0]
        seen = set()
        unique: List[str] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            val = r.get(col)
            if val is None or val == "":
                continue
            s = str(val).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            unique.append(s)
        return unique

    def _inject_known_values_into_sql(
        self,
        sql: str,
        *,
        session: Dict[str, Any],
        entities: Dict[str, Any],
        is_specific: bool,
    ) -> Tuple[str, Optional[str]]:
        """
        Replace common LLM placeholder tokens with known values.

        Safety net for cases where SQL generation emits `%s` / `?` placeholders.
        """
        if not sql:
            return sql, None

        sql_out = sql

        mrn = entities.get("medical_record_number") or session.get("last_patient_mrn")
        mrn_str = str(mrn).strip() if mrn is not None else ""
        mrn_safe = mrn_str.replace("'", "''")

        if is_specific and mrn_str:
            targeted_patterns = [
                r"(\bcast\s*\(\s*p\.medical_record_number\s+as\s+text\s*\)\s*=\s*)(%s|\?)",
                r"(\bcast\s*\(\s*patients\.medical_record_number\s+as\s+text\s*\)\s*=\s*)(%s|\?)",
                r"(\bp\.medical_record_number\s*=\s*)(%s|\?)",
                r"(\bmedical_record_number\s*=\s*)(%s|\?)",
            ]
            for pat in targeted_patterns:
                sql_out = re.sub(pat, rf"\g<1>'{mrn_safe}'", sql_out, flags=re.IGNORECASE)

            # Conservative fallback: only replace raw placeholders if the SQL is clearly MRN-filtered.
            if re.search(r"medical_record_number", sql_out, flags=re.IGNORECASE) and (
                re.search(r"%s", sql_out, flags=re.IGNORECASE) or re.search(r"=\s*\?", sql_out)
            ):
                sql_out = re.sub(r"%s", f"'{mrn_safe}'", sql_out, flags=re.IGNORECASE)
                sql_out = re.sub(r"\?", f"'{mrn_safe}'", sql_out)

        # If placeholders remain, return a clear error instead of executing invalid SQL.
        if re.search(r"%s", sql_out, flags=re.IGNORECASE) or re.search(r"=\s*\?", sql_out):
            return (
                sql,
                 "The generated SQL contains unresolved parameter placeholders (%s or ?). "
                 "Please rephrase your question with a medical record number (MRN).",
             )

        return sql_out, None
    
    def __init__(
        self,
        session_memory: Optional[SessionMemoryService] = None,
        intent_service: Optional[IntentDetectionService] = None,
        correction_service: Optional[SpellingCorrectionService] = None,
        scope_service: Optional[ScopeDetectionService] = None,
        entity_service: Optional[EntityExtractionService] = None,
        patient_details_service: Optional[PatientDetailsService] = None,
        statistics_service: Optional[StatisticsService] = None,
        audit_repo: Optional[AuditRepository] = None,
        hospital_repo: Optional[HospitalRepository] = None,
        access_control_repo: Optional[AccessControlRepository] = None,
        llm_client: Optional[Any] = None,
    ):
        self.session_memory = session_memory or SessionMemoryService()
        self.intent_service = intent_service or IntentDetectionService()
        self.correction_service = correction_service or SpellingCorrectionService()
        self.scope_service = scope_service or ScopeDetectionService()
        self.entity_service = entity_service or EntityExtractionService()
        self.patient_details_service = patient_details_service or PatientDetailsService()
        self.audit_repo = audit_repo or AuditRepository()
        self.hospital_repo = hospital_repo or HospitalRepository()
        self.access_control_repo = access_control_repo or AccessControlRepository()
        self.llm_client = llm_client or get_llm_client()
        self.rules_service = get_rules_service()
        self.advice_service = ClinicianAdviceService()
        self.statistics_service = statistics_service or StatisticsService(self.hospital_repo)
    
    def process_chat(
        self,
        raw_message: str,
        user_id: str,
        session_id: str,
        role: Optional[str] = None,
        approved: bool = False,
        correction_rejected: bool = False,
    ) -> Dict[str, Any]:
        """
        Main chat processing pipeline.
        
        Args:
            raw_message: User's raw message
            user_id: User ID
            session_id: Session ID
            role: User role (optional, will be looked up if not provided)
            approved: Whether correction was approved
            correction_rejected: Whether the user explicitly rejected the correction and wants to proceed with the original text
            
        Returns:
            Chat response dictionary
        """
        # Log request
        logger.info(f"📥 Received chat request: user_id={user_id}, session_id={session_id}, message='{raw_message}'")
        
        # Get role if not provided
        if not role:
            role = self.access_control_repo.get_user_role(user_id)
        logger.info(f"👤 User role: {role}")
        
        # ✅ Admin audit chat routing: if admin + audit question → route to audit DB
        if role == "admin" and self._looks_like_audit_question(raw_message):
            interaction_id = self.audit_repo.insert_interaction(
                user_id=user_id,
                session_id=session_id,
                role=role,
                intent="admin_audit_chat",
                approved=approved,
                raw_message=raw_message,
                final_message=raw_message,
            )
            try:
                result = self._handle_admin_audit_chat(user_id, raw_message)
                self.audit_repo.update_interaction(
                    interaction_id,
                    reply_text=result.get("text", ""),
                    row_count=result.get("data_json", {}).get("count", 0),
                )
                return result
            except Exception as e:
                self.audit_repo.update_interaction(interaction_id, ok=False, error=str(e))
                raise
        
        # Get or create session
        session = self.session_memory.get_session(session_id)
        previous_data_question = session.get("last_data_question")
        
        # Step 1: Spelling/grammar correction
        if correction_rejected:
            message = raw_message
            needs_approval = False
            logger.info("↩️ Correction rejected by user; proceeding with original message.")
        else:
            message, needs_approval = self.correction_service.correct_spelling_and_enhance_query(raw_message)
            if message != raw_message:
                logger.info(f"✏️ Correction: '{raw_message}' → '{message}' (needs_approval={needs_approval})")
        
        if needs_approval and not approved:
            interaction_id = self.audit_repo.insert_interaction(
                user_id=user_id,
                session_id=session_id,
                role=role,
                intent="approval_required",
                approved=False,
                raw_message=raw_message,
                final_message=message,
            )
            self.audit_repo.update_interaction(interaction_id, reply_text="Approval required.", row_count=0)
            return {
                "intent": "approval_required",
                "text": f"💬 I corrected your input to:\n\n**{message}**\n\nDo you want to proceed?",
                "original": raw_message,
                "corrected": message,
            }
        
        # Step 2: Detect intent
        if is_advice_style_question(message):
            intent = "advice"
        else:
            intent = self.intent_service.detect_intent(message, session)
        logger.info(f"🎯 Detected intent: {intent}")
        session["last_intent"] = intent
        if intent in ("data", "advice"):
            # Lightweight conversational continuity for follow-ups like "what else?"
            session["last_data_question"] = message
        self.session_memory.save_session(session_id, session)

        is_advice = intent == "advice"
        interaction_intent = intent
        
        # Create interaction record
        interaction_id = self.audit_repo.insert_interaction(
            user_id=user_id,
            session_id=session_id,
            role=role,
            intent=interaction_intent,
            approved=not correction_rejected,
            raw_message=raw_message,
            final_message=message,
        )

        if is_advice:
            result = self.advice_service.handle_advice_request(user_id=user_id, message=message)
            self.audit_repo.update_interaction(
                interaction_id,
                reply_text=result.get("text", ""),
                row_count=0,
                ok=True,
                intent="advice",
            )
            return result

        # STATISTICS PIPELINE (aggregate-only, no PHI)
        if intent == "statistics":
            result = self.statistics_service.handle(message)
            row_count = 0
            try:
                table = (result.get("data_json") or {}).get("table") or {}
                rows = table.get("rows") or []
                row_count = len(rows) if isinstance(rows, list) else 0
            except Exception:
                row_count = 0
            ok = not bool((result.get("meta") or {}).get("error"))
            self.audit_repo.update_interaction(
                interaction_id,
                reply_text=result.get("text", ""),
                row_count=row_count,
                ok=ok,
                error=(result.get("meta") or {}).get("error") if not ok else None,
                intent="statistics",
            )
            return result
        
        # If not data: respond with LLM (no SQL pipeline)
        if intent in ("social", "chat"):
            prompt = f"""{SYSTEM_PROMPT}

User: {message}

Reply naturally and concisely:
"""
            reply = self.llm_client.generate(prompt) or "Hello! 👋"
            self.audit_repo.update_interaction(interaction_id, reply_text=reply, row_count=0)
            return {"intent": intent, "text": reply, "data_json": {"type": "summary", "count": 0}}
        
        # DATA PIPELINE
        # Step 3: Decide scope
        is_specific = self.scope_service.decide_query_scope(message, session)
        
        # Cohort follow-up handling
        cohort_followup = False
        if (not is_specific) and (session.get("last_patient_mrns") or session.get("last_patient_ids")) and self.scope_service.is_cohort_followup(message):
            cohort_followup = True
        
        # Step 4: Extract entities
        entities = self.entity_service.extract_entities(message, session)
        entities.pop("patient_id", None)
        simple_mrn = self.entity_service.extract_medical_record_number_simple(message)
        if simple_mrn and entities.get("medical_record_number") is None:
            entities["medical_record_number"] = str(simple_mrn)
            logger.info("MRN [MEMORY] Extracted medical_record_number='%s' directly from message", simple_mrn)
        
        # Inject memory ONLY if query is about a specific patient (not general queries)
        # For general queries like "who was discharged", don't inject patient identifiers.
        # IMPORTANT: If a patient name is explicitly mentioned in the query, don't use cached MRN.
        # Only use cached MRN for pronouns like "he", "she", "this patient" when no name is mentioned.
        
        # Check if a patient name is explicitly mentioned in the message
        message_lower = message.lower()
        # Common patterns: "named X", "called X", "X's age", "how old is X", "is there a patient X", etc.
        has_explicit_name_pattern = any([
            "named" in message_lower,
            "called" in message_lower,
            "'s" in message_lower,  # e.g., "furat's age"
            "is there" in message_lower and "patient" in message_lower,  # "is there a patient named X"
            "how old is" in message_lower,  # "how old is X" - X is likely a name
            "what is" in message_lower and ("age" in message_lower or "old" in message_lower),  # "what is X's age"
        ])
        
        # If entity extraction found a patient_name, that takes precedence
        extracted_patient_name = entities.get("patient_name")
        if extracted_patient_name:
            logger.info(f"💾 [MEMORY] Patient name '{extracted_patient_name}' extracted from query - will search by name, NOT using cached MRN")
        elif has_explicit_name_pattern:
            # Explicit name pattern detected but entity extraction didn't extract it
            # Try to extract name from message directly
            logger.info(f"💾 [MEMORY] Explicit patient name pattern detected in query, NOT using cached MRN - will search by name")
            # Try to extract name from common patterns
            import re
            # Patterns: "how old is X", "is there a patient named X", "X's age", etc.
            name_match = None
            if "how old is" in message_lower:
                # Extract name after "how old is"
                match = re.search(r"how old is\s+([a-zA-Z\s]+)", message_lower, re.IGNORECASE)
                if match:
                    name_match = match.group(1).strip()
            elif "named" in message_lower:
                # Extract name after "named"
                match = re.search(r"named\s+([a-zA-Z\s]+)", message_lower, re.IGNORECASE)
                if match:
                    name_match = match.group(1).strip()
            elif "'s" in message_lower:
                # Extract name before "'s"
                match = re.search(r"([a-zA-Z\s]+)'s", message_lower, re.IGNORECASE)
                if match:
                    name_match = match.group(1).strip()
            
            if name_match:
                # Remove question marks and extra whitespace
                name_match = re.sub(r'[?\.!]+', '', name_match).strip()
                if name_match and len(name_match) > 1:  # Valid name
                    entities["patient_name"] = name_match
                    logger.info(f"💾 [MEMORY] Extracted patient_name='{name_match}' from message pattern")
        elif is_specific and entities.get("medical_record_number") is not None:
            logger.info(
                "MRN [MEMORY] Medical record number '%s' detected in query - using it",
                entities.get("medical_record_number"),
            )
        elif is_specific and entities.get("medical_record_number") is None:
            # No explicit identifier mentioned, safe to use cached MRN for pronouns/context.
            if session.get("last_patient_mrn") is not None:
                entities["medical_record_number"] = session["last_patient_mrn"]
                logger.info(
                    "MRN [MEMORY] Retrieved medical_record_number='%s' from Redis for SPECIFIC patient query (no explicit name)",
                    session["last_patient_mrn"],
                )
            elif session.get("last_patient"):
                entities["patient_name"] = session["last_patient"]
                logger.info(f"💾 [MEMORY] Retrieved patient_name={session['last_patient']} from Redis for SPECIFIC patient query (no explicit name)")
        elif not is_specific:
            if "patient_name" in entities and not any(word in message.lower() for word in ["patient", "patients"]):
                # Only remove patient_name if it's not explicitly mentioned in query
                logger.info(f"💾 [MEMORY] Removing patient_name from entities for GENERAL query")
                del entities["patient_name"]
        
        # Save new info to session memory (Redis)
        memory_updated = False
        if entities.get("patient_name"):
            session["last_patient"] = entities["patient_name"]
            memory_updated = True
            logger.info(f"💾 [MEMORY] Saving patient_name='{entities['patient_name']}' to Redis")
        if entities.get("medical_record_number"):
            session["last_patient_mrn"] = str(entities["medical_record_number"])
            memory_updated = True
            logger.info("MRN [MEMORY] Saving medical_record_number='%s' to Redis", entities["medical_record_number"])
        
        # Save session to Redis if updated
        if memory_updated:
            self.session_memory.save_session(session_id, session)
            logger.info(
                "💾 [MEMORY] ✅ Session saved to Redis: last_patient_mrn=%s, last_patient=%s",
                session.get("last_patient_mrn"),
                session.get("last_patient"),
            )
        
        # Prepare entities_for_prompt (copy of entities, may be modified)
        entities_for_prompt = entities.copy()
        if not is_specific:
            # Remove patient_id from entities for general queries
            entities_for_prompt.pop("patient_id", None)
            if "patient_name" in entities_for_prompt and not any(word in message.lower() for word in ["patient", "patients"]):
                entities_for_prompt.pop("patient_name", None)
        
        # Build enhanced query context
        if is_specific:
            # Check if we have patient_name in entities (name-based search)
            patient_name = entities_for_prompt.get("patient_name")
            patient_mrn = entities_for_prompt.get("medical_record_number") or session.get("last_patient_mrn")
            
            if patient_name and not patient_mrn:
                # Name-based search - search by name, not by ID
                rule_text = (
                    f"⚠️ CRITICAL: Search for patient by NAME '{patient_name}' in the patients table. "
                    f"Use WHERE TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.second_name, '') || ' ' || COALESCE(p.third_name, '') || ' ' || COALESCE(p.last_name, '')) ILIKE '%{patient_name}%' "
                    f"OR p.first_name ILIKE '%{patient_name}%' OR p.last_name ILIKE '%{patient_name}%'. "
                    "Prefer the `patients` table over `ap_patient` for patient details. "
                    "Do NOT filter on patients.id (patient id) for name-based searches. "
                    f"If no patient is found with this name, return 0 rows."
                )
                logger.info(f"💾 [MEMORY] Using patient_name='{patient_name}' for name-based search, NOT using cached MRN")
            elif patient_mrn:
                patient_mrn_str = str(patient_mrn)
                rule_text = (
                    f"⚠️ CRITICAL: The medical_record_number is '{patient_mrn_str}'. "
                    f"Use the `patients` table as the anchor and filter with CAST(p.medical_record_number AS TEXT) = '{patient_mrn_str}'. "
                    "Join other tables as needed to answer the request (labs, orders, results, etc.). "
                    "Do NOT compare this value against p.id because patients.id is numeric and record or MRN identifiers can be alphanumeric. "
                    "Only fall back to legacy ap_* patient tables if the requested data truly exists only there. "
                    "Do NOT use placeholders like %s or ?. Use the actual medical record number value directly. "
                    "Do not use subqueries or name-based lookups when this record identifier is known."
                )
                logger.info("MRN [MEMORY] Using medical_record_number='%s' for SQL generation", patient_mrn_str)
            else:
                rule_text = (
                    "⚠️ IMPORTANT: This is a specific-patient question, but no medical record number (MRN) is known. "
                    "Do NOT filter by patients.id (patient id). Prefer using an MRN if provided, otherwise use a name-based search."
                )
        elif cohort_followup:
            cohort_mrns = session.get("last_patient_mrns") or []
            safe_mrns = [
                "'" + str(mrn).replace("'", "''") + "'"
                for mrn in cohort_mrns
                if mrn not in (None, "")
            ]
            cohort_in_list = ", ".join(safe_mrns) if safe_mrns else "''"
            rule_text = (
                "⚠️ IMPORTANT: The user is referring to the SAME COHORT of patients that were returned "
                "in the previous query. Restrict the query to ONLY those patients by using "
                f"WHERE CAST(p.medical_record_number AS TEXT) IN ({cohort_in_list}) "
                "or an equivalent IN filter. Do NOT include patients outside this list."
            )
        else:
            rule_text = (
                "⚠️ IMPORTANT: This question is general (not about a specific patient). "
                "Do NOT restrict by MRN unless explicitly requested. Query all patients matching the date or criteria mentioned."
            )
        
        # If this looks like a follow-up question, include the prior data question inside "User said"
        # so the SQL generator's table detection can pick up missing domain context (e.g., labs).
        message_for_sql = message
        tl = (message or "").lower()
        if previous_data_question and any(
            marker in tl
            for marker in [
                "what else",
                "anything else",
                "any other",
                "also",
                "and what",
                "what about",
                "what more",
            ]
        ):
            prev = (previous_data_question or "").strip()
            cur = (message or "").strip()
            if prev and prev != cur:
                message_for_sql = f"{message} (Follow-up to previous request: {previous_data_question})"

        enhanced_query = (
            f"User said: {message_for_sql}. "
            f"Entities (including memory): {json.dumps(entities_for_prompt, ensure_ascii=False)}. "
            f"{rule_text}"
        )
        
        logger.info(
            "🧠 Query Context Mode: "
            + (
                "Specific (single patient)"
                if is_specific
                else ("Cohort (previous result)" if cohort_followup else "General (all patients)")
            )
        )
        
        # Check business rules before processing query
        is_allowed, rule_error = self.rules_service.check_query_restrictions(
            user_message=message,
            entities=entities_for_prompt,
            is_specific=is_specific
        )
        if not is_allowed:
            logger.warning(f"🚫 Query blocked by business rules: {rule_error}")
            self.audit_repo.update_interaction(interaction_id, ok=False, error=rule_error, row_count=0)
            return {
                "intent": "data",
                "text": rule_error or "This query is not allowed due to business rules.",
                "data_json": {"count": 0, "table": []},
            }

        if is_specific and self._is_patient_overview_request(message):
            overview_result = self._handle_patient_overview_request(
                user_id=user_id,
                session_id=session_id,
                interaction_id=interaction_id,
                entities=entities_for_prompt,
                session=session,
            )
            if overview_result is not None:
                return overview_result
        
        # Use CrewAI for data queries (only if enabled in config)
        # Note: CrewAI is slower (30-60s) because it uses multiple sequential LLM calls
        # Standard pipeline is faster (5-10s) because it makes direct service calls
        if settings.use_crewai:
            try:
                from app.crewai.crew import build_medai_crew
                
                logger.info("🤖 Using CrewAI for query processing (slower but more intelligent)")
                crew = build_medai_crew(
                    user_message=message,
                    user_id=user_id,
                    role=role,
                    enhanced_query=enhanced_query,
                    entities=entities_for_prompt,
                    is_specific=is_specific
                )
                
                # Set a timeout for CrewAI processing (60 seconds max)
                # If it takes too long, fall back to standard pipeline
                CREWAI_TIMEOUT = 60
                
                # Note: CrewAI doesn't support timeout directly, so we'll catch timeout exceptions
                # and fall back to standard pipeline
                result = crew.kickoff(inputs={
                    "message": message,
                    "user_id": user_id,
                    "role": role,
                    "enhanced_query": enhanced_query,
                    "entities": entities_for_prompt,
                    "is_specific": is_specific
                })
                
                # Parse CrewAI result
                # CrewAI returns a CrewOutput object
                logger.info(f"🤖 CrewAI result type: {type(result)}")
                
                # Try to extract structured data from result
                # CrewAI CrewOutput object has various attributes
                text = ""
                data_json = {}
                sql = ""
                
                # Debug: Log all available attributes
                logger.debug(f"🤖 CrewAI result attributes: {[attr for attr in dir(result) if not attr.startswith('_')]}")
                
                # Method 1: Check if result has .raw attribute (CrewOutput object)
                if hasattr(result, 'raw'):
                    raw_result = result.raw
                    logger.debug(f"🤖 CrewAI result.raw type: {type(raw_result)}, value: {str(raw_result)[:300]}")
                    if isinstance(raw_result, dict):
                        text = raw_result.get("summary", "")
                        data_json = raw_result.get("data_json", {})
                        sql = raw_result.get("sql", "")
                    elif isinstance(raw_result, str):
                        # Try to parse as JSON string
                        try:
                            parsed = json.loads(raw_result)
                            if isinstance(parsed, dict):
                                text = parsed.get("summary", "")
                                data_json = parsed.get("data_json", {})
                                sql = parsed.get("sql", "")
                        except:
                            # Try ast.literal_eval for Python dict strings
                            try:
                                import ast
                                parsed = ast.literal_eval(raw_result)
                                if isinstance(parsed, dict):
                                    text = parsed.get("summary", "")
                                    data_json = parsed.get("data_json", {})
                                    sql = parsed.get("sql", "")
                            except:
                                text = raw_result
                                data_json = {"type": "summary", "count": 0}
                    else:
                        text = str(raw_result)
                        data_json = {"type": "summary", "count": 0}
                
                # Method 2: Check if result has .tasks_output attribute
                if not text and hasattr(result, 'tasks_output'):
                    tasks_output = result.tasks_output
                    logger.debug(f"🤖 CrewAI result.tasks_output type: {type(tasks_output)}, length: {len(tasks_output) if isinstance(tasks_output, list) else 'N/A'}")
                    if isinstance(tasks_output, list) and len(tasks_output) > 0:
                        # Get the last task output (usually the final result)
                        last_output = tasks_output[-1]
                        logger.debug(f"🤖 Last task output type: {type(last_output)}, value: {str(last_output)[:300]}")
                        if isinstance(last_output, dict):
                            text = last_output.get("summary", "")
                            data_json = last_output.get("data_json", {})
                            sql = last_output.get("sql", "")
                        elif isinstance(last_output, str):
                            try:
                                parsed = json.loads(last_output)
                                if isinstance(parsed, dict):
                                    text = parsed.get("summary", "")
                                    data_json = parsed.get("data_json", {})
                                    sql = parsed.get("sql", "")
                            except:
                                # Try ast.literal_eval
                                try:
                                    import ast
                                    parsed = ast.literal_eval(last_output)
                                    if isinstance(parsed, dict):
                                        text = parsed.get("summary", "")
                                        data_json = parsed.get("data_json", {})
                                        sql = parsed.get("sql", "")
                                except:
                                    text = last_output
                
                # Method 3: Try to parse the string representation
                if not text:
                    result_str = str(result)
                    logger.debug(f"🤖 CrewAI result string (first 500 chars): {result_str[:500]}")
                    # Try to parse as Python dict literal
                    try:
                        import ast
                        # Check if it looks like a dict
                        if result_str.strip().startswith("{") or ("'summary'" in result_str and "'data_json'" in result_str):
                            parsed = ast.literal_eval(result_str)
                            if isinstance(parsed, dict):
                                text = parsed.get("summary", "")
                                data_json = parsed.get("data_json", {})
                                sql = parsed.get("sql", "")
                    except Exception as e:
                        logger.debug(f"🤖 Failed to parse result string: {e}")
                
                # Method 4: Also check if result itself is a dict (some CrewAI versions)
                if not text and isinstance(result, dict):
                    text = result.get("summary", "")
                    data_json = result.get("data_json", {})
                    sql = result.get("sql", "")
                
                # Method 5: If text still contains dict string, try to extract just the summary
                if text and isinstance(text, str) and text.strip().startswith("{") and ("'summary'" in text or '"summary"' in text):
                    try:
                        import ast
                        logger.debug(f"🤖 Attempting to parse text as dict: {text[:200]}...")
                        parsed = ast.literal_eval(text)
                        if isinstance(parsed, dict):
                            extracted_text = parsed.get("summary", text)
                            extracted_data_json = parsed.get("data_json", {})
                            extracted_sql = parsed.get("sql", "")
                            logger.debug(f"🤖 Successfully extracted: text='{extracted_text[:50]}...', has_data_json={bool(extracted_data_json)}, has_sql={bool(extracted_sql)}")
                            text = extracted_text
                            if not data_json and extracted_data_json:
                                data_json = extracted_data_json
                            if not sql and extracted_sql:
                                sql = extracted_sql
                    except Exception as e:
                        logger.debug(f"🤖 Failed to parse text as dict: {e}")
                        # Try JSON parsing as fallback
                        try:
                            parsed = json.loads(text)
                            if isinstance(parsed, dict):
                                text = parsed.get("summary", text)
                                if not data_json:
                                    data_json = parsed.get("data_json", {})
                                if not sql:
                                    sql = parsed.get("sql", "")
                        except:
                            pass
                
                # Final fallback
                if not text:
                    text = "Query processed successfully."
                
                # Log parsed result
                row_count = len(data_json.get("table", [])) if isinstance(data_json, dict) else 0
                logger.info(f"🤖 Parsed CrewAI result: text='{text[:100]}...', data_json.count={row_count}, has_sql={bool(sql)}")
                
                # Extract rows from data_json if available
                rows = data_json.get("table", []) if isinstance(data_json, dict) else []
                row_count = len(rows) if isinstance(rows, list) else 0
                
                # Check result limit for CrewAI results
                is_within_limit, limit_error = self.rules_service.check_result_limit(row_count)
                if not is_within_limit:
                    logger.warning(f"🚫 Result limit exceeded in CrewAI result: {limit_error}")
                    self.audit_repo.update_interaction(interaction_id, ok=False, error=limit_error, row_count=row_count)
                    return {
                        "intent": "data",
                        "text": limit_error or f"This query returned {row_count} results, which exceeds the maximum limit.",
                        "data_json": {"count": row_count, "table": []},
                    }
                
                if isinstance(data_json, dict) and isinstance(rows, list):
                    sanitized_rows = self._strip_patient_id_fields_from_rows(rows)
                    data_json["table"] = sanitized_rows
                    if isinstance(data_json.get("columns"), list):
                        data_json["columns"] = self._strip_patient_id_fields_from_columns(data_json.get("columns"))
                    rows = sanitized_rows
                    row_count = len(rows)

                unique_mrns = self._extract_unique_mrns_from_rows(rows)
                if unique_mrns:
                    session["last_patient_mrns"] = unique_mrns
                    session["last_patient_ids"] = None

                    if len(unique_mrns) == 1:
                        session["last_patient_mrn"] = unique_mrns[0]
                        name_cols = [
                            k
                            for k in rows[0].keys()
                            if "name" in k.lower() and ("full_name" in k.lower() or "patient" in k.lower())
                        ]
                        if name_cols and rows[0].get(name_cols[0]):
                            session["last_patient"] = str(rows[0].get(name_cols[0]))
                        self.session_memory.save_session(session_id, session)
                        logger.info(
                            "💾 [MEMORY] ✅ Saved to Redis: medical_record_number=%s, patient_name=%s",
                            session["last_patient_mrn"],
                            session.get("last_patient", "N/A"),
                        )
                    else:
                        self.session_memory.save_session(session_id, session)
                        logger.info("💾 [MEMORY] ✅ Saved cohort to Redis: %s MRNs", len(unique_mrns))
                
                if sql:
                    self.audit_repo.update_interaction(interaction_id, sql_query=sql)
                self.audit_repo.update_interaction(interaction_id, reply_text=text, row_count=row_count)
                
                logger.info(f"💬 Final response: text='{text[:100]}...', data_json.count={row_count}")
                
                return {
                    "intent": "data",
                    "text": text,
                    "data_json": data_json,
                }
                
            except ImportError as e:
                logger.warning(f"⚠️ CrewAI not available, falling back to standard pipeline: {e}")
                # Fall through to standard pipeline
            except TimeoutError as e:
                logger.warning(f"⏱️ CrewAI timeout after 60 seconds, falling back to standard pipeline: {e}")
                # Fall through to standard pipeline
            except Exception as e:
                error_msg = str(e)
                # Check if it's a timeout-related error
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    logger.warning(f"⏱️ CrewAI timeout, falling back to standard pipeline: {e}")
                else:
                    logger.error(f"❌ CrewAI failed: {e}", exc_info=True)
                    logger.warning("⚠️ Falling back to standard pipeline")
                # Fall through to standard pipeline
        else:
            logger.info("📋 CrewAI disabled - using fast standard pipeline")
        
        # FALLBACK: Standard pipeline (if CrewAI fails or is not available)
        logger.info("📋 Using standard SQL pipeline")
        
        # Stage 1: SQL generation
        ok_sql, sql_body, err_sql = self._call_sql_generator(enhanced_query, user_id, interaction_id)
        if not ok_sql:
            self.audit_repo.update_interaction(interaction_id, ok=False, error=f"SQL generation failed: {err_sql}")
            raise Exception(f"SQL generation failed: {err_sql}")
        
        sql = sql_body.get("sql_query") or sql_body.get("sql", "")
        sql, placeholder_error = self._inject_known_values_into_sql(
            sql,
            session=session,
            entities=entities_for_prompt,
            is_specific=is_specific,
        )
        self.audit_repo.update_interaction(interaction_id, sql_query=sql)
        if placeholder_error:
            logger.warning(f"🚫 SQL query blocked - unresolved placeholders: {placeholder_error}")
            self.audit_repo.update_interaction(interaction_id, ok=False, error=placeholder_error, row_count=0)
            return {
                "intent": "data",
                "text": placeholder_error,
                "data_json": {"count": 0, "table": []},
            }
        
        # Check business rules on generated SQL query
        is_allowed, rule_error = self.rules_service.check_query_restrictions(
            user_message=message,
            sql_query=sql,
            entities=entities_for_prompt,
            is_specific=is_specific
        )
        if not is_allowed:
            logger.warning(f"🚫 SQL query blocked by business rules: {rule_error}")
            self.audit_repo.update_interaction(interaction_id, ok=False, error=rule_error, row_count=0)
            return {
                "intent": "data",
                "text": rule_error or "This query is not allowed due to business rules.",
                "data_json": {"count": 0, "table": []},
            }
        
        # Placeholder injection handled earlier by _inject_known_values_into_sql.
        
        logger.info(f"📜 Generated SQL: {sql[:200]}..." if len(sql) > 200 else f"📜 Generated SQL: {sql}")
        
        # Stage 2: Validation + execution
        ok_val, val_body, err_val = self._call_validator(sql, role, user_id, interaction_id)
        
        validation_msg = ""
        rows: List[Dict[str, Any]] = []
        validation_valid = ok_val
        if isinstance(val_body, dict):
            validation_result = val_body.get("validation_result", {})
            validation_msg = validation_result.get("message", "")
            rows = validation_result.get("rows", [])
            validation_valid = validation_result.get("valid", ok_val)
        
        validation_msg_lower = (validation_msg or "").lower()
        if (
            not ok_val
            or validation_valid is False
            or any(
                marker in validation_msg_lower
                for marker in [
                    "sql execution error",
                    "database execution error",
                    "validation failed",
                    "forbidden",
                    "not allowed",
                ]
            )
        ):
            msg = validation_msg or err_val or "Validation failed."
            self.audit_repo.update_interaction(interaction_id, ok=False, error=msg, row_count=0)
            return {
                "intent": "data",
                "text": f"⚠️ Unable to execute the query: {msg}",
                "meta": {"error": msg},
            }
        
        row_count = len(rows)
        logger.info(f"📊 Query returned {row_count} row(s)")
        
        # Check result limit
        is_within_limit, limit_error = self.rules_service.check_result_limit(row_count)
        if not is_within_limit:
            logger.warning(f"🚫 Result limit exceeded: {limit_error}")
            self.audit_repo.update_interaction(interaction_id, ok=False, error=limit_error, row_count=row_count)
            return {
                "intent": "data",
                "text": limit_error or f"This query returned {row_count} results, which exceeds the maximum limit.",
                "data_json": {"count": row_count, "table": []},
            }
        
        if row_count == 0:
            logger.warning(f"⚠️ No rows returned for query")
        self.audit_repo.update_interaction(interaction_id, row_count=row_count)
        
        rows = self._strip_patient_id_fields_from_rows(rows)

        unique_mrns = self._extract_unique_mrns_from_rows(rows)
        if unique_mrns:
            session["last_patient_mrns"] = unique_mrns
            session["last_patient_ids"] = None

            if len(unique_mrns) == 1:
                session["last_patient_mrn"] = unique_mrns[0]
                name_cols = [
                    k
                    for k in rows[0].keys()
                    if "name" in k.lower() and ("full_name" in k.lower() or "patient" in k.lower())
                ]
                if name_cols and rows[0].get(name_cols[0]):
                    session["last_patient"] = str(rows[0].get(name_cols[0]))
                self.session_memory.save_session(session_id, session)
                logger.info(
                    "💾 [MEMORY] ✅ Saved to Redis: medical_record_number=%s, patient_name=%s",
                    session["last_patient_mrn"],
                    session.get("last_patient", "N/A"),
                )
            else:
                self.session_memory.save_session(session_id, session)
                logger.info("💾 [MEMORY] ✅ Saved cohort to Redis: %s MRNs", len(unique_mrns))
        
        # Stage 3: Formatter
        columns = list(rows[0].keys()) if rows else []
        ok_fmt, fmt_body, err_fmt = self._call_formatter(rows, columns, message, interaction_id)
        
        if not ok_fmt:
            self.audit_repo.update_interaction(interaction_id, ok=False, error=f"Formatter failed: {err_fmt}")
            raise Exception(f"Formatter failed: {err_fmt}")
        
        text = fmt_body.get("summary") or "Done."
        data_json = fmt_body.get("json") or {}
        
        logger.info(f"💬 Final response: text='{text[:100]}...', data_json.count={data_json.get('count', 0)}")
        self.audit_repo.update_interaction(interaction_id, reply_text=text, row_count=row_count)
        
        return {
            "intent": "data",
            "text": text,
            "data_json": data_json,
        }
    
    def _call_sql_generator(self, enhanced_query: str, user_id: str, interaction_id: Optional[int]) -> Tuple[bool, Dict[str, Any], str]:
        """Call SQL generator service."""
        payload = {"user_id": user_id, "text": enhanced_query}
        for path in ("/generate_sql", "/generate"):
            ok, body, err = post_json_logged(
                interaction_id,
                "sql_generator",
                f"{settings.sql_gen_url}{path}",
                payload,
                audit_service=self.audit_repo,
            )
            if ok and ("sql_query" in body or "sql" in body):
                logger.info(f"📜 [Stage 1 Output] {body if ok else err}")
                return True, body, ""
        return False, {}, err
    
    def _call_validator(self, sql: str, role: Optional[str], user_id: str, interaction_id: Optional[int]) -> Tuple[bool, Dict[str, Any], str]:
        """Call validator service."""
        payload = {"user_id": user_id, "sql_query": sql}
        for path in ("/validate_and_execute", "/validate"):
            ok, body, err = post_json_logged(
                interaction_id,
                "validator",
                f"{settings.validator_url}{path}",
                payload,
                audit_service=self.audit_repo,
            )
            if ok and isinstance(body, dict):
                rows = body.get("validation_result", {}).get("rows", [])
                sanitized_rows = self._strip_patient_id_fields_from_rows(rows)
                logger.info(f"📊 [Stage 2 Output] {json.dumps(sanitized_rows, indent=2, ensure_ascii=False)}")
                return True, body, ""
        return False, {}, err
    
    def _call_formatter(self, rows: List[Dict[str, Any]], columns: List[str], user_intent: str, interaction_id: Optional[int]) -> Tuple[bool, Dict[str, Any], str]:
        """Call formatter service."""
        payload = {
            "user_intent": user_intent,
            "result_rows": rows,
            "column_meta": [{"name": c} for c in (columns or [])],
            "role": "doctor",
        }
        for path in ("/format_results", "/format"):
            ok, body, err = post_json_logged(
                interaction_id,
                "formatter",
                f"{settings.formatter_url}{path}",
                payload,
                audit_service=self.audit_repo,
            )
            if ok:
                logger.info(f"💬 [Stage 3 Output] {body.get('summary')}")
                return True, body, ""
        return False, {}, err
    
    def _looks_like_audit_question(self, text: str) -> bool:
        """Check if text looks like an admin audit question."""
        _AUDIT_HINTS = [
            "history",
            "yesterday",
            "logs",
            "audit",
            "services",
            "what did the chatbot do",
            "what did it do",
            "for user",
            "session",
            "events",
        ]
        tl = (text or "").lower()
        return any(h in tl for h in _AUDIT_HINTS)

    def _is_patient_overview_request(self, text: str) -> bool:
        """Detect broad 'tell me everything about this patient' requests."""
        tl = (text or "").lower()
        identifier_terms = [
            "patient",
            "record",
            "mrn",
            "medical record",
            "medical number",
        ]
        if not any(term in tl for term in identifier_terms):
            return False

        overview_hints = [
            "what information can you give me",
            "what info can you give me",
            "what the info you can give me",
            "what can you tell me about",
            "tell me about the patient",
            "everything about the patient",
            "all information about the patient",
            "all info about the patient",
            "full details about the patient",
            "patient profile",
            "patient details",
            "all info for record",
            "all information for record",
            "all details for record",
            "full details for record",
            "everything about record",
            "all info for mrn",
            "all information for mrn",
        ]
        if any(hint in tl for hint in overview_hints):
            return True

        return bool(
            (
                ("info" in tl or "information" in tl or "details" in tl)
                and ("give me" in tl or "about" in tl or "show" in tl)
            )
            or ("tell me" in tl and "about" in tl)
            or ("everything" in tl and any(term in tl for term in identifier_terms))
            or (
                "all" in tl
                and ("info" in tl or "information" in tl or "details" in tl)
                and any(term in tl for term in identifier_terms)
            )
        )

    def _handle_patient_overview_request(
        self,
        user_id: str,
        session_id: str,
        interaction_id: int,
        entities: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Return a comprehensive patient profile for broad patient-info questions."""
        supported_sections = self.patient_details_service.get_supported_sections_for_user(user_id)
        supported_text = ", ".join(supported_sections) if supported_sections else "basic patient details"

        medical_record_number = entities.get("medical_record_number") or session.get("last_patient_mrn")
        patient_name = entities.get("patient_name") or session.get("last_patient")

        lookup_field = "medical_record_number"
        lookup_value = str(medical_record_number) if medical_record_number else None
        display_value = f"record {lookup_value}" if lookup_value else None

        if not lookup_value:
            return {
                "intent": "data",
                "text": (
                    "I can provide patient information from these database areas: "
                    f"{supported_text}. Please provide a medical record number (MRN) so I can load the full profile."
                ),
                "data_json": {
                    "type": "summary",
                    "count": 0,
                    "available_sections": supported_sections,
                },
            }

        logger.info(
            "MRN Routing broad patient overview request through patient-details profile for %s using %s",
            display_value,
            lookup_field,
        )

        sql = self.patient_details_service.build_patient_details_sql(
            user_id,
            lookup_value,
            lookup_field=lookup_field,
        )
        if not sql:
            self.audit_repo.update_interaction(
                interaction_id,
                ok=False,
                error="No patient details allowed for this user.",
                row_count=0,
            )
            return {
                "intent": "data",
                "text": "⚠️ Patient details are not available for your current access level.",
                "data_json": {"count": 0, "table": []},
            }

        ok_val, val_body, err_val = self._call_validator(sql, None, user_id, interaction_id)
        validation_result = val_body.get("validation_result", {}) if isinstance(val_body, dict) else {}
        validation_msg = validation_result.get("message", "")
        validation_valid = validation_result.get("valid", ok_val)
        rows = validation_result.get("rows", [])

        if not ok_val or validation_valid is False:
            msg = validation_msg or err_val or "Validation failed."
            self.audit_repo.update_interaction(interaction_id, ok=False, error=msg, row_count=0)
            return {
                "intent": "data",
                "text": f"⚠️ Unable to load the full patient profile: {msg}",
                "data_json": {"count": 0, "table": []},
            }

        if not rows:
            self.audit_repo.update_interaction(
                interaction_id,
                reply_text="No data found for this patient.",
                sql_query=sql,
                row_count=0,
            )
            return {
                "intent": "data",
                "text": (
                    f"No data was found for {display_value}. "
                    f"I can normally provide these patient details from the database: {supported_text}."
                ),
                "data_json": {
                    "count": 0,
                    "table": [],
                    "available_sections": supported_sections,
                },
            }

        patient = self.patient_details_service.transform_patient_data(rows[0])
        available_sections = self.patient_details_service.get_available_sections(patient)
        section_text = ", ".join(available_sections) if available_sections else "basic patient details"
        summary = (
            f"I can provide these patient details from the database for {display_value}: "
            f"{section_text}. I pulled the currently available profile fields below."
        )

        if patient.get("medical_record_number"):
            session["last_patient_mrn"] = str(patient["medical_record_number"])
        if patient.get("full_name"):
            session["last_patient"] = patient["full_name"]
        self.session_memory.save_session(session_id, session)

        self.audit_repo.update_interaction(
            interaction_id,
            reply_text=summary,
            sql_query=sql,
            row_count=1,
        )
        return {
            "intent": "data",
            "text": summary,
            "data_json": {
                "type": "record",
                "count": 1,
                "title": "Patient details",
                "record": patient,
                "columns": list(patient.keys()),
            },
        }
    
    def _require_admin(self, admin_user_id: str):
        """Require admin role for user."""
        role = self.access_control_repo.get_user_role(admin_user_id)
        if role != "admin":
            raise Exception("Admin privileges required.")
    
    def _handle_admin_audit_chat(self, admin_user_id: str, message: str) -> Dict[str, Any]:
        """
        Handle admin audit questions via chat.
        Routes to audit DB instead of hospital DB.
        """
        self._require_admin(admin_user_id)
        
        # Parse intent (heuristic for now, can add CrewAI later)
        parsed = self._admin_audit_intent_heuristic(message)
        
        action = (parsed.get("action") or "history").lower()
        limit = int(parsed.get("limit") or 50)
        
        if action == "event":
            event_id = int(parsed.get("event_id") or 0)
            if event_id <= 0:
                return {"intent": "admin_audit", "text": "⚠️ Provide a valid event_id.", "data_json": {"type": "summary", "count": 0}}
            try:
                data = self.audit_repo.query_event(event_id)
                return {
                    "intent": "admin_audit",
                    "text": f"🧾 Event {event_id} details.",
                    "data_json": {"type": "table", "count": 1, "table": [data], "columns": ["interaction", "service_calls"]},
                }
            except ValueError as e:
                return {"intent": "admin_audit", "text": f"⚠️ {str(e)}", "data_json": {"type": "summary", "count": 0}}
        
        if action == "session":
            session_id = parsed.get("session_id")
            if not session_id:
                return {"intent": "admin_audit", "text": "⚠️ Provide a session_id.", "data_json": {"type": "summary", "count": 0}}
            rows = self.audit_repo.query_history(user_id=None, session_id=session_id, start_utc=None, end_utc=None, limit=limit)
            return {
                "intent": "admin_audit",
                "text": f"📚 {len(rows)} event(s) for session {session_id}.",
                "data_json": {"type": "table", "count": len(rows), "table": rows, "columns": list(rows[0].keys()) if rows else []},
            }
        
        if action == "search":
            q = (parsed.get("q") or "").strip()
            if not q:
                return {"intent": "admin_audit", "text": "⚠️ Provide a search query.", "data_json": {"type": "summary", "count": 0}}
            rows = self.audit_repo.search(q, limit=limit)
            return {
                "intent": "admin_audit",
                "text": f"🔎 Found {len(rows)} match(es) for: \"{q}\".",
                "data_json": {"type": "table", "count": len(rows), "table": rows, "columns": list(rows[0].keys()) if rows else []},
            }
        
        # Default: history
        user_id = parsed.get("user_id")
        start_utc, end_utc = self.audit_repo.parse_range(parsed.get("range") or "")
        rows = self.audit_repo.query_history(user_id=user_id, session_id=None, start_utc=start_utc, end_utc=end_utc, limit=limit)
        
        title = "📚 History"
        if parsed.get("range"):
            title += f" ({parsed.get('range')})"
        if user_id:
            title += f" for {user_id}"
        
        return {
            "intent": "admin_audit",
            "text": f"{title}: {len(rows)} event(s).",
            "data_json": {"type": "table", "count": len(rows), "table": rows, "columns": list(rows[0].keys()) if rows else []},
        }
    
    def _admin_audit_intent_heuristic(self, message: str) -> Dict[str, Any]:
        """Parse admin audit intent using heuristics."""
        import re
        tl = (message or "").lower()
        out: Dict[str, Any] = {"action": "history", "limit": 50}
        
        if "search" in tl:
            out["action"] = "search"
            out["q"] = message.replace("search", "", 1).strip() or ""
            return out
        
        if "session" in tl:
            out["action"] = "session"
            m = re.search(r"(session[_\-\s]?\w+)", message, flags=re.I)
            if m:
                out["session_id"] = m.group(1).strip()
            return out
        
        if "event" in tl:
            out["action"] = "event"
            m = re.search(r"\b(\d{1,10})\b", message)
            if m:
                out["event_id"] = int(m.group(1))
            return out
        
        if "yesterday" in tl:
            out["range"] = "yesterday"
        elif "today" in tl:
            out["range"] = "today"
        
        m = re.search(r"\buser\s+(u\d+)\b", tl)
        if m:
            out["user_id"] = m.group(1)
        
        m2 = re.search(r"\blimit\s+(\d+)\b", tl)
        if m2:
            out["limit"] = int(m2.group(1))
        
        return out


# Global instance
_chat_orchestrator = ChatOrchestratorService()
