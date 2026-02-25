"""Chat orchestrator service - main business logic for chat pipeline."""
import json
import time
import logging
import sys
import os
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

logger = logging.getLogger(__name__)
# Ensure logger propagates to root logger (which has file handler)
logger.setLevel(logging.INFO)
logger.propagate = True  # Allow logs to propagate to root logger
# Don't add separate handlers - use root logger's handlers


class ChatOrchestratorService:
    """Main orchestrator service for chat pipeline."""
    
    def __init__(
        self,
        session_memory: Optional[SessionMemoryService] = None,
        intent_service: Optional[IntentDetectionService] = None,
        correction_service: Optional[SpellingCorrectionService] = None,
        scope_service: Optional[ScopeDetectionService] = None,
        entity_service: Optional[EntityExtractionService] = None,
        patient_details_service: Optional[PatientDetailsService] = None,
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
    
    def process_chat(
        self,
        raw_message: str,
        user_id: str,
        session_id: str,
        role: Optional[str] = None,
        approved: bool = False,
    ) -> Dict[str, Any]:
        """
        Main chat processing pipeline.
        
        Args:
            raw_message: User's raw message
            user_id: User ID
            session_id: Session ID
            role: User role (optional, will be looked up if not provided)
            approved: Whether correction was approved
            
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
        
        # Step 1: Spelling/grammar correction
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
        intent = self.intent_service.detect_intent(message, session)
        logger.info(f"🎯 Detected intent: {intent}")
        session["last_intent"] = intent
        self.session_memory.save_session(session_id, session)
        
        # Create interaction record
        interaction_id = self.audit_repo.insert_interaction(
            user_id=user_id,
            session_id=session_id,
            role=role,
            intent=intent,
            approved=True,
            raw_message=raw_message,
            final_message=message,
        )
        
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
        if (not is_specific) and session.get("last_patient_ids") and self.scope_service.is_cohort_followup(message):
            cohort_followup = True
        
        # Step 4: Extract entities
        entities = self.entity_service.extract_entities(message, session)
        
        # Auto-inject "last 2 weeks" date filter for patient list queries without date criteria
        if not is_specific:
            message_lower = message.lower()
            # Check if this is a patient list query
            is_patient_list_query = any(phrase in message_lower for phrase in [
                "all patients", "every patient", "all patient", "list of patients", 
                "give me a list of patients", "show me all patients", "get all patients"
            ])
            
            # Check if query already has a date filter
            has_date_filter = any(keyword in message_lower for keyword in [
                "today", "yesterday", "this week", "this month", "last week", "last month",
                "date", "admitted", "discharged", "between", "from", "to", "since", "after", "before",
                "last 2 weeks", "past 2 weeks", "two weeks", "2 weeks", "january", "february", "march",
                "april", "may", "june", "july", "august", "september", "october", "november", "december"
            ])
            
            # If it's a patient list query without date filter, inject "last 2 weeks"
            if is_patient_list_query and not has_date_filter:
                # Add date filter to entities
                entities["date"] = "last 2 weeks"
                logger.info("📅 Auto-injecting 'last 2 weeks' date filter for patient list query without date criteria")
        
        # Inject memory ONLY if query is about a specific patient (not general queries)
        # For general queries like "who was discharged", don't inject patient_id
        # IMPORTANT: If a patient name is explicitly mentioned in the query, don't use cached patient_id
        # Only use cached patient_id if no patient name is mentioned (e.g., "how old is he?")
        
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
            logger.info(f"💾 [MEMORY] Patient name '{extracted_patient_name}' extracted from query - will search by name, NOT using cached patient_id")
            # Clear any cached patient_id to force name-based search
            if "patient_id" in entities:
                del entities["patient_id"]
        elif has_explicit_name_pattern:
            # Explicit name pattern detected but entity extraction didn't extract it
            # Try to extract name from message directly
            logger.info(f"💾 [MEMORY] Explicit patient name pattern detected in query, NOT using cached patient_id - will search by name")
            # Clear cached patient_id to force name-based search
            if "patient_id" in entities:
                del entities["patient_id"]
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
        elif is_specific and entities.get("patient_id") is None:
            # No explicit name mentioned, safe to use cached patient_id for pronouns/context
            if session.get("last_patient_id") is not None:
                entities["patient_id"] = session["last_patient_id"]
                logger.info(f"💾 [MEMORY] Retrieved patient_id={session['last_patient_id']} from Redis for SPECIFIC patient query (no explicit name)")
            elif session.get("last_patient"):
                entities["patient_name"] = session["last_patient"]
                logger.info(f"💾 [MEMORY] Retrieved patient_name={session['last_patient']} from Redis for SPECIFIC patient query (no explicit name)")
        elif not is_specific:
            # For general queries, clear any patient_id from entities to avoid confusion
            if "patient_id" in entities:
                logger.info(f"💾 [MEMORY] Removing patient_id from entities for GENERAL query")
                del entities["patient_id"]
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
        if entities.get("patient_id") is not None:
            session["last_patient_id"] = str(entities["patient_id"])
            memory_updated = True
            logger.info(f"💾 [MEMORY] Saving patient_id={entities['patient_id']} to Redis")
        
        # Auto-fetch missing ID from DB if only name is known
        if session.get("last_patient") and not session.get("last_patient_id"):
            pid = self.hospital_repo.fetch_patient_id_by_name(session["last_patient"])
            if pid:
                session["last_patient_id"] = str(pid)
                memory_updated = True
                logger.info(f"💾 [MEMORY] Auto-fetched patient_id={pid} from DB and saving to Redis")
        
        # Save session to Redis if updated
        if memory_updated:
            self.session_memory.save_session(session_id, session)
            logger.info(f"💾 [MEMORY] ✅ Session saved to Redis: last_patient_id={session.get('last_patient_id')}, last_patient={session.get('last_patient')}")
        
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
            patient_id = entities_for_prompt.get("patient_id") or session.get("last_patient_id")
            
            if patient_name and not entities_for_prompt.get("patient_id"):
                # Name-based search - search by name, not by ID
                rule_text = (
                    f"⚠️ CRITICAL: Search for patient by NAME '{patient_name}' in p.full_name, p.first_name, or p.last_name. "
                    f"Use WHERE p.full_name ILIKE '%{patient_name}%' OR p.first_name ILIKE '%{patient_name}%' OR p.last_name ILIKE '%{patient_name}%'. "
                    f"Do NOT use patient_id. This is a name-based search. "
                    f"If no patient is found with this name, return 0 rows."
                )
                logger.info(f"💾 [MEMORY] Using patient_name='{patient_name}' for name-based search, NOT using cached patient_id")
            elif patient_id:
                # ID-based search - use patient_id
                patient_id_str = str(patient_id)
                rule_text = (
                    f"⚠️ CRITICAL: The patient_id is {patient_id_str}. "
                    f"ALWAYS use p.key = '{patient_id_str}' (or e.patient_key = '{patient_id_str}') in WHERE clauses. "
                    "Do NOT use placeholders like %s or ?. Use the actual patient_id value directly. "
                    "Do not use subqueries or name-based lookups. "
                    "If the user refers to 'he', 'she', or 'this patient', use this patient_id directly."
                )
                logger.info(f"💾 [MEMORY] Using patient_id={patient_id_str} from Redis for SQL generation")
            else:
                rule_text = (
                    "⚠️ IMPORTANT: The patient_id is known. ALWAYS use patient_id in WHERE clauses. "
                    "Do not use subqueries or name-based lookups if patient_id exists. "
                    "Only use patient name if patient_id is completely missing. "
                    "If the user refers to 'he', 'she', or 'this patient', use the saved patient_id directly."
                )
        elif cohort_followup:
            rule_text = (
                "⚠️ IMPORTANT: The user is referring to the SAME COHORT of patients that were returned "
                "in the previous query. Restrict the query to ONLY those patients by using "
                f"WHERE patient_id IN ({', '.join(str(pid) for pid in (session.get('last_patient_ids') or []))}) "
                "or an equivalent IN filter. Do NOT include patients outside this list."
            )
        else:
            rule_text = (
                "⚠️ IMPORTANT: This question is general (not about a specific patient). "
                "Do NOT restrict by patient_id. Query all patients matching the date or criteria mentioned."
            )
        
        # Add note about default date filter if it was auto-injected
        date_filter_note = ""
        if not is_specific and entities_for_prompt.get("date") == "last 2 weeks":
            date_filter_note = " ⚠️ IMPORTANT: The user asked for a list of patients without specifying a date range. Apply a default filter for the LAST 2 WEEKS (14 days) based on admission date (e.created_at) or encounter date. Use: TO_TIMESTAMP(e.created_at / 1000.0) >= CURRENT_DATE - INTERVAL '14 days' OR similar date filter. This is a default filter to prevent returning too many results."
        
        enhanced_query = (
            f"User said: {message}. "
            f"Entities (including memory): {json.dumps(entities_for_prompt, ensure_ascii=False)}. "
            f"{date_filter_note} "
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
                
                # Save patient_id to Redis memory if query results contain patient_id
                if rows and isinstance(rows, list) and len(rows) > 0 and isinstance(rows[0], dict):
                    pid_cols = [k for k in rows[0].keys() if "patient_id" in k.lower()]
                    if pid_cols:
                        col = pid_cols[0]
                        try:
                            patient_ids = [r.get(col) for r in rows if r.get(col) is not None]
                            session["last_patient_ids"] = [int(pid) for pid in patient_ids if pid is not None]
                            
                            # If only one patient returned, also save as last_patient_id for pronoun resolution
                            if len(patient_ids) == 1 and patient_ids[0] is not None:
                                session["last_patient_id"] = str(patient_ids[0])
                                # Also try to get patient name if available
                                name_cols = [k for k in rows[0].keys() if "name" in k.lower() and ("full_name" in k.lower() or "patient" in k.lower())]
                                if name_cols and rows[0].get(name_cols[0]):
                                    session["last_patient"] = str(rows[0].get(name_cols[0]))
                                self.session_memory.save_session(session_id, session)
                                logger.info(f"💾 [MEMORY] ✅ Saved to Redis: patient_id={session['last_patient_id']}, patient_name={session.get('last_patient', 'N/A')}")
                            else:
                                # Multiple patients - save cohort
                                self.session_memory.save_session(session_id, session)
                                logger.info(f"💾 [MEMORY] ✅ Saved cohort to Redis: {len(patient_ids)} patient_ids")
                        except Exception as e:
                            logger.warning(f"⚠️ [MEMORY] Failed to extract patient_ids: {e}")
                            session["last_patient_ids"] = None
                
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
        self.audit_repo.update_interaction(interaction_id, sql_query=sql)
        
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
        
        # Auto-inject patient_id if placeholder '?' or '%s' is used
        if session.get("last_patient_id"):
            pid = str(session["last_patient_id"])
            original_sql = sql
            if "?" in sql:
                sql = sql.replace("?", pid)
                logger.info(f"🧩 [MEMORY] Replaced '?' placeholder with patient_id={pid} from Redis")
            if "%s" in sql:
                sql = sql.replace("%s", pid)
                logger.info(f"🧩 [MEMORY] Replaced '%s' placeholder with patient_id={pid} from Redis")
            if sql != original_sql:
                self.audit_repo.update_interaction(interaction_id, sql_query=sql)
                logger.info(f"💾 [MEMORY] ✅ SQL updated with patient_id from Redis memory")
        
        logger.info(f"📜 Generated SQL: {sql[:200]}..." if len(sql) > 200 else f"📜 Generated SQL: {sql}")
        
        # Stage 2: Validation + execution
        ok_val, val_body, err_val = self._call_validator(sql, role, user_id, interaction_id)
        
        validation_msg = ""
        rows: List[Dict[str, Any]] = []
        if isinstance(val_body, dict):
            validation_msg = val_body.get("validation_result", {}).get("message", "")
            rows = val_body.get("validation_result", {}).get("rows", [])
        
        if not ok_val or "❌" in (validation_msg or ""):
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
        
        # Save patient_id to Redis memory if query results contain patient_id
        if rows and isinstance(rows[0], dict):
            pid_cols = [k for k in rows[0].keys() if "patient_id" in k.lower()]
            if pid_cols:
                col = pid_cols[0]
                try:
                    patient_ids = [r.get(col) for r in rows if r.get(col) is not None]
                    session["last_patient_ids"] = [int(pid) for pid in patient_ids if pid is not None]
                    
                    # If only one patient returned, also save as last_patient_id for pronoun resolution
                    if len(patient_ids) == 1 and patient_ids[0] is not None:
                        session["last_patient_id"] = str(patient_ids[0])
                        # Also try to get patient name if available
                        name_cols = [k for k in rows[0].keys() if "name" in k.lower() and ("full_name" in k.lower() or "patient" in k.lower())]
                        if name_cols and rows[0].get(name_cols[0]):
                            session["last_patient"] = str(rows[0].get(name_cols[0]))
                        self.session_memory.save_session(session_id, session)
                        logger.info(f"💾 [MEMORY] ✅ Saved to Redis: patient_id={session['last_patient_id']}, patient_name={session.get('last_patient', 'N/A')}")
                    else:
                        # Multiple patients - save cohort
                        self.session_memory.save_session(session_id, session)
                        logger.info(f"💾 [MEMORY] ✅ Saved cohort to Redis: {len(patient_ids)} patient_ids")
                except Exception as e:
                    logger.warning(f"⚠️ [MEMORY] Failed to extract patient_ids: {e}")
                    session["last_patient_ids"] = None
        
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
                logger.info(f"📊 [Stage 2 Output] {json.dumps(rows, indent=2, ensure_ascii=False)}")
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

