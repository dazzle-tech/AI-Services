"""Result formatting service."""
import json
import re
import logging
from typing import Dict, Any, List, Optional, Any
from app.models.schemas import FormatterRequest, FormatterResponse, OutputJSON, OutputType
from app.infrastructure.llm.llm_client import get_llm_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class FormattingService:
    """Service for formatting query results."""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client or get_llm_client()
    
    def format(self, payload: FormatterRequest) -> FormatterResponse:
        """
        Format database result into human-like summary.
        
        Args:
            payload: Formatter request payload
            
        Returns:
            Formatter response
        """
        rows = payload.result_rows or []
        count = len(rows)
        
        # Ordered columns for UI rendering
        columns = list(rows[0].keys()) if count > 0 else None
        
        # Check if this is a patient list query that used default date filter
        user_intent_lower = (payload.user_intent or "").lower()
        is_patient_list_query = any(phrase in user_intent_lower for phrase in [
            "all patients", "every patient", "all patient", "list of patients", 
            "give me a list of patients", "show me all patients", "get all patients"
        ])
        has_explicit_date = any(keyword in user_intent_lower for keyword in [
            "today", "yesterday", "this week", "this month", "last week", "last month",
            "date", "between", "from", "to", "since", "after", "before",
            "last 2 weeks", "past 2 weeks", "two weeks", "2 weeks"
        ])
        used_default_filter = is_patient_list_query and not has_explicit_date
        
        # Human-facing summary
        if count == 0:
            # Generate a more specific error message based on the query type
            summary = self._generate_no_results_message(payload.user_intent)
            if used_default_filter:
                summary += " (Note: Showing results from the last 2 weeks. If you need a different date range, please specify it in your query.)"
            out_type = OutputType.SUMMARY
        else:
            # Check if this is a list query - generate brief summary but keep table view
            is_list_query = self._is_list_query(payload.user_intent)
            
            if is_list_query:
                # For list queries, generate a brief summary while still showing the table
                summary = self._run_llm_summary(payload.user_intent, rows, is_list_query=True)
            elif self._detect_conciseness_mode(payload.user_intent, row_count=count):
                summary = self._run_llm_summary(payload.user_intent, rows)
            else:
                summary = f"{count} records found."
            
            # Add note about default date filter if it was used
            if used_default_filter:
                summary += " (Note: Showing patients from the last 2 weeks. If you need a different date range, please specify it in your query.)"
            
            out_type = OutputType.TABLE
        
        return FormatterResponse(
            summary=summary,
            json=OutputJSON(
                type=out_type,
                count=count,
                table=rows,
                columns=columns,
            ),
        )
    
    def _is_list_query(self, user_intent: str) -> bool:
        """Check if the query is asking for a list."""
        text = (user_intent or "").lower().strip()
        list_keywords = ["list", "show me", "give me a list", "show all", "get all", "all of"]
        return any(kw in text for kw in list_keywords)
    
    def _detect_conciseness_mode(self, user_intent: str, row_count: int = 0) -> bool:
        """Decide if we should use concise mode."""
        text = (user_intent or "").lower().strip()
        tokens = text.split()
        
        # List keywords - always show table/list format, regardless of row count
        if self._is_list_query(user_intent):
            return False  # Always use table view for list queries
        
        # Plural keywords that suggest multiple records should be shown in table
        plural_keywords = ["allergies", "medications", "medicines", "prescriptions", "diagnoses", 
                          "conditions", "symptoms", "tests", "procedures", "records", "patients",
                          "all ", "what are", "what are the"]
        
        # For plural questions with multiple records, prefer table view over summary
        if any(kw in text for kw in plural_keywords) and row_count > 1:
            return False
        
        short_fact_keywords = ["who", "what", "when", "how old", "age", "dob", "date of birth"]
        yes_no_patterns = [
            "are they", "are all", "is he", "is she", "is this patient", "is the patient",
            "do they", "does he", "does she", "any ", "any of them",
            "currently admitted", "still admitted", "still in hospital", "discharged",
        ]
        
        is_short_question = text.endswith("?") and len(tokens) <= 10
        
        if any(k in text for k in short_fact_keywords):
            return True
        if any(p in text for p in yes_no_patterns):
            return True
        if is_short_question:
            return True
        if row_count > 0 and row_count <= 5:
            return True
        
        return False
    
    def _run_llm_summary(self, user_intent: str, rows: List[Dict[str, Any]], is_list_query: bool = False) -> str:
        """Generate natural language summary using LLM."""
        if not rows:
            return "No data found for that query."
        
        result_json = json.dumps(rows, indent=2, ensure_ascii=False)
        concise_mode = self._detect_conciseness_mode(user_intent, row_count=len(rows))
        row_count = len(rows)
        
        # Detect if question is about plural things (allergies, medications, etc.)
        plural_keywords = ["allergies", "medications", "medicines", "prescriptions", "diagnoses", 
                          "conditions", "symptoms", "tests", "procedures", "records", "patients"]
        is_plural_question = any(kw in user_intent.lower() for kw in plural_keywords)
        has_multiple_records = row_count > 1
        
        # Special handling for list queries - descriptive summary with table view
        if is_list_query:
            tone_instruction = f"""
You are MedAI, a hospital assistant providing a descriptive summary for a list query.
The user asked for a list, and the full table will be shown below.
Write a clear, descriptive summary that explains what was found in the list.
Include key details from the data (names, dates, diagnoses, etc.) in a natural way.

For {row_count} record{'s' if row_count != 1 else ''}:
- If 1 record: Describe that one patient/record with key details (name, admission date, diagnosis, etc.)
- If multiple records: Summarize the list, mentioning key patients and their details

Examples:
- "Found 1 admitted patient: Emily Johnson, admitted on October 1, 2025, for observation."
- "There are 3 currently admitted patients: John Doe (admitted Oct 1 for surgery), Jane Smith (admitted Oct 2 for treatment), and Bob Wilson (admitted Oct 3 for observation)."
- "The list includes 2 patients: Patient 1001 (Emily Johnson, admitted Oct 1 for observation) and Patient 1002 (John Doe, admitted Oct 2 for surgery)."

Be descriptive and include actual data from the results. Write in natural, conversational language.
"""
        # Special handling for plural questions with multiple records
        elif is_plural_question and has_multiple_records:
            tone_instruction = """
You are MedAI, a clinical assistant that provides clear answers about multiple patients.
The user asked about multiple records (allergies, medications, etc.).
IMPORTANT: You must mention ALL patients in your answer, not just one.
Format: "Patient [ID] has [allergies/medications]: [list]. Patient [ID] has [list]."
Or: "Found {count} patients: Patient [ID] has [X], Patient [ID] has [Y], etc."
Be direct and list all patients mentioned in the data.
"""
        elif concise_mode:
            tone_instruction = """
You are MedAI, a clinical assistant that provides short, human-like answers.
Use natural phrasing (e.g., "The patient was born on July 25, 1990.").
Avoid robotic key-value formats like "Date of Birth: July 25, 1990".
Be direct, factual, and polite.
Do NOT start with phrases like "Here is the output" or "Based on the result".
Never explain your reasoning — just provide the answer.
"""
        else:
            tone_instruction = """
You are MedAI, a hospital assistant that summarizes data clearly and naturally.
Keep it short and readable (like you are speaking to a doctor).
Avoid phrases like "The database shows" or "According to records".
If there are multiple patients, you must mention all of them and their details.
"""
        
        prompt = f"""
{tone_instruction}

User question:
{user_intent}

Database result (JSON):
{result_json}

Write a single short and natural answer:
"""
        
        try:
            reply = self.llm_client.generate(prompt)
            # Post-processing cleanup
            reply = re.sub(r"(?i)^(here is|based on|the result|output)[:,\s]*", "", reply).strip()
            reply = re.sub(r"\s{2,}", " ", reply)
            reply = re.sub(r"[""\"']", "", reply).strip()
            
            if reply and not reply[0].isupper():
                reply = reply[0].upper() + reply[1:]
            
            if not reply:
                first = rows[0]
                reply = ". ".join(f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in first.items()) + "."
            
            return reply
        except Exception as e:
            logger.error(f"LLM summary error: {e}")
            return "Unable to summarize the result."
    
    def _generate_no_results_message(self, user_intent: str) -> str:
        """
        Generate a clear, specific error message when no results are found.
        
        Args:
            user_intent: The user's original question
            
        Returns:
            A clear error message
        """
        import re
        intent_lower = user_intent.lower()
        
        # Check for patient name patterns
        patient_name_patterns = [
            r"how old is\s+([a-zA-Z\s]+)",
            r"is there.*patient.*named\s+([a-zA-Z\s]+)",
            r"patient.*named\s+([a-zA-Z\s]+)",
            r"([a-zA-Z\s]+)'s\s+(age|allergies|medications|diagnosis)",
            r"what is\s+([a-zA-Z\s]+)'s",
        ]
        
        for pattern in patient_name_patterns:
            match = re.search(pattern, intent_lower, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean up the name (remove question marks, extra spaces)
                name = re.sub(r'[?\.!]+', '', name).strip()
                if name and len(name) > 1:
                    # Capitalize first letter
                    name = name[0].upper() + name[1:] if name else name
                    return f"No patient named '{name}' was found in the database."
        
        # Check for specific question types
        if "how old" in intent_lower or "age" in intent_lower:
            return "No patient information was found for that question."
        elif "is there" in intent_lower and "patient" in intent_lower:
            return "No matching patient was found in the database."
        elif "admitted" in intent_lower or "discharged" in intent_lower:
            return "No matching admission or discharge records were found."
        elif "allergies" in intent_lower:
            return "No allergy information was found."
        elif "medications" in intent_lower or "medicines" in intent_lower:
            return "No medication information was found."
        else:
            return "No matching records were found for that question."


# Global instance
_formatting_service = FormattingService()

