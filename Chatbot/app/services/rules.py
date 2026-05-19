"""Business rules and restrictions service for query validation."""
import re
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class BusinessRulesService:
    """Service for enforcing business rules and restrictions on queries."""
    
    def __init__(self, rules_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the business rules service.
        
        Args:
            rules_config: Optional rules configuration dictionary.
                         If not provided, loads from rules.json or uses default rules.
        """
        if rules_config is not None:
            self.rules = rules_config
        else:
            # Try to load from JSON file first
            rules_file = Path(__file__).parent.parent.parent / "data" / "rules.json"
            if rules_file.exists():
                try:
                    with open(rules_file, 'r', encoding='utf-8') as f:
                        loaded_rules = json.load(f)
                    # Convert JSON string patterns to Python regex patterns
                    self.rules = self._normalize_rules(loaded_rules)
                    logger.info(f"✅ Loaded business rules from {rules_file}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load rules.json: {e}. Using default rules.")
                    self.rules = self._get_default_rules()
            else:
                logger.info("📋 rules.json not found, using default rules")
                self.rules = self._get_default_rules()
    
    def _normalize_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize rules loaded from JSON (convert string patterns to regex-compatible format)."""
        # JSON patterns are already strings, so they should work with re.search
        # Just ensure all patterns are properly formatted
        normalized = rules.copy()
        
        # Normalize forbidden_queries patterns
        if "forbidden_queries" in normalized and "patterns" in normalized["forbidden_queries"]:
            for pattern in normalized["forbidden_queries"]["patterns"]:
                if "pattern" in pattern:
                    # JSON patterns use double backslashes, which is correct for Python strings
                    # No conversion needed - they'll work as-is with re.search
                    pass
        
        return normalized
    
    def _get_default_rules(self) -> Dict[str, Any]:
        """Get default business rules."""
        return {
            "max_results": {
                "enabled": True,
                "limit": 1000,  # Maximum number of rows to return
                "message": "This query would return too many results. Please refine your query with specific criteria (e.g., date range, patient name, or other filters)."
            },
            "forbidden_queries": {
                "enabled": True,
                "patterns": [
                    {
                        "pattern": r"\b(all|every|entire)\s+(patient|patients)\b",
                        "case_sensitive": False,
                        "message": "I cannot return all patients in the hospital as this would be too many results. Please specify a date range, patient name, or other criteria to narrow down your query."
                    },
                    {
                        "pattern": r"\bshow\s+(me\s+)?all\s+(patient|patients)\b",
                        "case_sensitive": False,
                        "message": "I cannot return all patients in the hospital as this would be too many results. Please specify a date range, patient name, or other criteria to narrow down your query."
                    },
                    {
                        "pattern": r"\blist\s+(all\s+)?(patient|patients)\b",
                        "case_sensitive": False,
                        "message": "I cannot return all patients in the hospital as this would be too many results. Please specify a date range, patient name, or other criteria to narrow down your query."
                    },
                    {
                        "pattern": r"\bget\s+(all|every)\s+(patient|patients)\b",
                        "case_sensitive": False,
                        "message": "I cannot return all patients in the hospital as this would be too many results. Please specify a date range, patient name, or other criteria to narrow down your query."
                    },
                    {
                        "pattern": r"\bcount\s+(all|every)\s+(patient|patients)\b",
                        "case_sensitive": False,
                        "message": "Counting all patients would require processing too many records. Please specify a date range or other criteria to narrow down your query."
                    },
                    {
                        "pattern": r"\bselect\s+\*\s+from\s+ap_patient\s*(where\s+1\s*=\s*1)?\s*$",
                        "case_sensitive": False,
                        "message": "This query would return all patients, which is not allowed. Please add specific filters."
                    },
                ]
            },
            "required_filters": {
                "enabled": True,
                "rules": [
                    {
                        "table": "ap_patient",
                        "when": "querying all patients",
                        "required_filters": ["date_range", "patient_name", "patient_id", "status", "ward", "room"],
                        "message": "When querying patients, you must include at least one filter: date range, patient name/ID, status, ward, or room number."
                    }
                ]
            },
            "date_range_limits": {
                "enabled": True,
                "max_days": 365,  # Maximum date range in days
                "message": "The requested date range is too large. Please limit your query to a maximum of 365 days."
            },
            "sensitive_data": {
                "enabled": True,
                "restrictions": [
                    {
                        "pattern": r"\b(ssn|social\s+security|credit\s+card|bank\s+account)\b",
                        "case_sensitive": False,
                        "message": "I cannot provide sensitive financial or identification information."
                    }
                ]
            }
        }
    
    def check_query_restrictions(
        self,
        user_message: str,
        sql_query: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
        is_specific: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a query violates any business rules.
        
        Args:
            user_message: The user's natural language query
            sql_query: Optional SQL query to check
            entities: Optional extracted entities
            is_specific: Whether the query is about a specific patient
            
        Returns:
            Tuple of (is_allowed, error_message)
            - is_allowed: True if query is allowed, False if restricted
            - error_message: None if allowed, error message if restricted
        """
        # Check forbidden query patterns
        if self.rules.get("forbidden_queries", {}).get("enabled", True):
            forbidden_patterns = self.rules["forbidden_queries"].get("patterns", [])
            message_lower = user_message.lower()
            
            # Check if this is a patient list query
            is_patient_list_query = any(phrase in message_lower for phrase in [
                "all patients", "every patient", "all patient", "list of patients", 
                "list patients", "list patient",
                "give me a list of patients", "show me all patients", "get all patients"
            ])
            
            for rule in forbidden_patterns:
                pattern = rule.get("pattern", "")
                case_sensitive = rule.get("case_sensitive", False)
                error_message = rule.get("message", "This query is not allowed.")
                
                # Keep patient list queries allowed; result limits still apply later in the pipeline.
                if is_patient_list_query and ("patient" in pattern.lower() or "patients" in pattern.lower()):
                    logger.info(f"✅ Allowing patient list query without forcing a default date filter: {pattern}")
                    continue
                
                if case_sensitive:
                    if re.search(pattern, user_message):
                        logger.warning(f"🚫 Query blocked by rule: {pattern}")
                        return False, error_message
                else:
                    if re.search(pattern, message_lower):
                        logger.warning(f"🚫 Query blocked by rule: {pattern}")
                        return False, error_message
        
        # Check bulk operations restrictions
        if self.rules.get("bulk_operations", {}).get("enabled", True):
            restrictions = self.rules["bulk_operations"].get("restrictions", [])
            message_lower = user_message.lower()
            
            for restriction in restrictions:
                pattern = restriction.get("pattern", "")
                case_sensitive = restriction.get("case_sensitive", False)
                error_message = restriction.get("message", "Bulk operations are not allowed.")
                
                if case_sensitive:
                    if re.search(pattern, user_message):
                        logger.warning(f"🚫 Query blocked - bulk operation: {pattern}")
                        return False, error_message
                else:
                    if re.search(pattern, message_lower):
                        logger.warning(f"🚫 Query blocked - bulk operation: {pattern}")
                        return False, error_message
        
        # Check SQL query for forbidden patterns (if SQL is provided)
        if sql_query:
            sql_lower = sql_query.lower().strip()
            sql_upper = sql_query.upper()
            
            # Check SQL restrictions (forbidden keywords)
            if self.rules.get("sql_restrictions", {}).get("enabled", True):
                forbidden_keywords = self.rules["sql_restrictions"].get("forbidden_keywords", [])
                for keyword in forbidden_keywords:
                    # Use word boundaries to match whole words only (not substrings like "CREATE" in "created_at")
                    # Match keyword as a whole word, case-insensitive
                    pattern = rf'\b{re.escape(keyword)}\b'
                    if re.search(pattern, sql_query, re.IGNORECASE):
                        error_message = self.rules["sql_restrictions"].get(
                            "message",
                            f"SQL operations like {keyword} are not allowed. This system is read-only."
                        )
                        logger.warning(f"🚫 SQL query blocked - forbidden keyword: {keyword}")
                        return False, error_message
                
                # Check SQL forbidden patterns
                forbidden_patterns = self.rules["sql_restrictions"].get("forbidden_patterns", [])
                for rule in forbidden_patterns:
                    pattern = rule.get("pattern", "")
                    case_sensitive = rule.get("case_sensitive", False)
                    error_message = rule.get("message", "This SQL query pattern is not allowed.")
                    
                    if case_sensitive:
                        if re.search(pattern, sql_query):
                            logger.warning(f"🚫 SQL query blocked by pattern: {pattern}")
                            return False, error_message
                    else:
                        if re.search(pattern, sql_lower):
                            logger.warning(f"🚫 SQL query blocked by pattern: {pattern}")
                            return False, error_message
            
            # Check performance restrictions
            if self.rules.get("performance_restrictions", {}).get("enabled", True):
                # Count JOINs
                join_count = len(re.findall(r"\bjoin\b", sql_lower))
                max_joins = self.rules["performance_restrictions"].get("max_joins", 3)
                if join_count > max_joins:
                    error_message = self.rules["performance_restrictions"].get(
                        "message",
                        f"This query has too many JOINs ({join_count}). Please simplify your query."
                    )
                    logger.warning(f"🚫 SQL query blocked - too many JOINs: {join_count}")
                    return False, error_message
                
                # Count subqueries
                subquery_count = len(re.findall(r"\(\s*select\s+", sql_lower))
                max_subqueries = self.rules["performance_restrictions"].get("max_subqueries", 2)
                if subquery_count > max_subqueries:
                    error_message = self.rules["performance_restrictions"].get(
                        "message",
                        f"This query has too many subqueries ({subquery_count}). Please simplify your query."
                    )
                    logger.warning(f"🚫 SQL query blocked - too many subqueries: {subquery_count}")
                    return False, error_message
                
                # Check for WHERE clause requirement
                require_where = self.rules["performance_restrictions"].get("require_where_clause", True)
                if require_where:
                    # Check if query has WHERE clause (but allow SELECT COUNT(*) which might not need WHERE)
                    has_where = "where" in sql_lower
                    has_limit = "limit" in sql_lower
                    is_count_only = re.search(r"select\s+count\s*\(\s*\*\s*\)\s+from", sql_lower)
                    
                    if not has_where and not has_limit and not is_count_only:
                        # Check if it's a simple SELECT with specific columns and LIMIT
                        if not re.search(r"select\s+[^,]+(?:,\s*[^,]+)*\s+from\s+\w+\s+limit\s+\d+", sql_lower):
                            error_message = self.rules["performance_restrictions"].get(
                                "message",
                                "This query should include a WHERE clause or LIMIT to prevent full table scans."
                            )
                            logger.warning("🚫 SQL query blocked - missing WHERE clause")
                            return False, error_message
            
            # Check column restrictions
            if self.rules.get("column_restrictions", {}).get("enabled", True):
                forbidden_columns = self.rules["column_restrictions"].get("forbidden_columns", [])
                for col in forbidden_columns:
                    # Check if forbidden column is selected
                    if re.search(rf"\b{re.escape(col)}\b", sql_lower):
                        error_message = self.rules["column_restrictions"].get(
                            "message",
                            f"Access to column '{col}' is restricted."
                        )
                        logger.warning(f"🚫 SQL query blocked - forbidden column: {col}")
                        return False, error_message
            
            # Check aggregate restrictions
            if self.rules.get("aggregate_restrictions", {}).get("enabled", True):
                aggregate_functions = ["count", "sum", "avg", "max", "min", "group_concat"]
                aggregate_count = sum(1 for func in aggregate_functions if re.search(rf"\b{func}\s*\(", sql_lower))
                max_aggregates = self.rules["aggregate_restrictions"].get("max_aggregate_functions", 5)
                if aggregate_count > max_aggregates:
                    error_message = self.rules["aggregate_restrictions"].get(
                        "message",
                        f"This query has too many aggregate functions ({aggregate_count}). Please simplify your query."
                    )
                    logger.warning(f"🚫 SQL query blocked - too many aggregate functions: {aggregate_count}")
                    return False, error_message
            
            # Check forbidden query patterns in SQL
            if self.rules.get("forbidden_queries", {}).get("enabled", True):
                forbidden_patterns = self.rules["forbidden_queries"].get("patterns", [])
                
                for rule in forbidden_patterns:
                    pattern = rule.get("pattern", "")
                    case_sensitive = rule.get("case_sensitive", False)
                    error_message = rule.get("message", "This query is not allowed.")
                    
                    # Check SQL-specific patterns
                    if "select" in pattern.lower() or "from" in pattern.lower():
                        if case_sensitive:
                            if re.search(pattern, sql_query):
                                logger.warning(f"🚫 SQL query blocked by rule: {pattern}")
                                return False, error_message
                        else:
                            if re.search(pattern, sql_lower):
                                logger.warning(f"🚫 SQL query blocked by rule: {pattern}")
                                return False, error_message
        
        # Check sensitive data restrictions
        if self.rules.get("sensitive_data", {}).get("enabled", True):
            restrictions = self.rules["sensitive_data"].get("restrictions", [])
            message_lower = user_message.lower()
            
            for restriction in restrictions:
                pattern = restriction.get("pattern", "")
                case_sensitive = restriction.get("case_sensitive", False)
                error_message = restriction.get("message", "This query involves sensitive data that cannot be accessed.")
                
                if case_sensitive:
                    if re.search(pattern, user_message):
                        logger.warning(f"🚫 Query blocked - sensitive data: {pattern}")
                        return False, error_message
                else:
                    if re.search(pattern, message_lower):
                        logger.warning(f"🚫 Query blocked - sensitive data: {pattern}")
                        return False, error_message
        
        # Check future date restrictions
        future_section = self.rules.get("future_date_restrictions") or {}
        if future_section.get("enabled", False):
            message_lower = user_message.lower()

            # Check for future date keywords (relative).
            future_keywords = ["tomorrow", "next week", "next month", "next year", "future", "upcoming"]
            blocks = any(keyword in message_lower for keyword in future_keywords)

            # Check for explicit future year references (absolute).
            if not blocks:
                from datetime import datetime

                current_year = datetime.now().year
                for match in re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", user_message):
                    try:
                        year = int(match)
                    except ValueError:
                        continue
                    if year > current_year:
                        blocks = True
                        break

            if blocks:
                error_message = future_section.get(
                    "message",
                    "I cannot query data for future dates. Please specify a date in the past or present.",
                )
                logger.warning("🚫 Query blocked - future date restriction")
                return False, error_message
        
        # Check historical data limits
        historical_section = self.rules.get("historical_data_limits") or {}
        if historical_section.get("enabled", False):
            max_years_back = historical_section.get("max_years_back", 10)
            from datetime import datetime

            current_year = datetime.now().year
            for match in re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", user_message):
                try:
                    year = int(match)
                except ValueError:
                    continue
                if current_year - year > max_years_back:
                    error_message = historical_section.get(
                        "message",
                        f"I cannot query data older than {max_years_back} years. Please specify a more recent date range.",
                    )
                    logger.warning(f"🚫 Query blocked - historical data limit: {year}")
                    return False, error_message
        
        # Check text search restrictions
        text_search_rules = self.rules.get("text_search_restrictions", {})
        if text_search_rules.get("enabled", True):
            # Check for LIKE or ILIKE patterns that might be too broad
            if sql_query:
                sql_lower = sql_query.lower()
                # Check for LIKE '%...%' patterns without LIMIT
                like_patterns = re.findall(r"like\s+['\"]%[^%]*%['\"]", sql_lower)
                if like_patterns:
                    has_limit = "limit" in sql_lower
                    # Default to *not* requiring LIMIT so text-search queries can run,
                    # with max_results/timeouts acting as the primary safety rails.
                    require_limit = text_search_rules.get("require_limit", False)
                    if require_limit and not has_limit:
                        error_message = text_search_rules.get(
                            "message",
                            "Text search queries must include LIMIT clauses to prevent performance issues."
                        )
                        logger.warning("🚫 SQL query blocked - text search without LIMIT")
                        return False, error_message
        
        # If query is about a specific patient, it's generally allowed
        if is_specific:
            logger.info("✅ Query allowed - specific patient query")
            return True, None
        
        # Check if general query has required filters
        if not is_specific and self.rules.get("required_filters", {}).get("enabled", True):
            # Check if query mentions date range, patient name, or other filters
            message_lower = user_message.lower()
            has_date_filter = any(keyword in message_lower for keyword in [
                "today", "yesterday", "this week", "this month", "last week", "last month",
                "date", "admitted", "discharged", "between", "from", "to", "since", "after", "before"
            ])
            has_patient_filter = entities and (entities.get("patient_name") or entities.get("medical_record_number"))
            has_other_filter = any(keyword in message_lower for keyword in [
                "ward", "room", "status", "diagnosis", "doctor", "nurse", "department"
            ])
            
            # Allow broad patient-list requests without injecting a synthetic date range.
            if any(phrase in message_lower for phrase in ["all patients", "every patient", "all patient", "list of patients", "list patients", "list patient", "give me a list of patients"]):
                logger.info("✅ Allowing 'all patients' query without applying a default date filter")
                pass
        
        logger.info("✅ Query allowed - passed all rule checks")
        return True, None
    
    def check_result_limit(self, row_count: int) -> Tuple[bool, Optional[str]]:
        """
        Check if result count exceeds maximum allowed.
        
        Args:
            row_count: Number of rows returned
            
        Returns:
            Tuple of (is_within_limit, error_message)
        """
        if not self.rules.get("max_results", {}).get("enabled", True):
            return True, None
        
        max_limit = self.rules["max_results"].get("limit", 1000)
        if row_count > max_limit:
            error_message = self.rules["max_results"].get(
                "message",
                f"This query returned {row_count} results, which exceeds the maximum limit of {max_limit}. Please refine your query with more specific criteria."
            )
            logger.warning(f"🚫 Result limit exceeded: {row_count} > {max_limit}")
            return False, error_message
        
        return True, None
    
    def get_rules_summary(self) -> Dict[str, Any]:
        """Get a summary of all active rules."""
        return {
            "max_results": {
                "enabled": self.rules.get("max_results", {}).get("enabled", True),
                "limit": self.rules.get("max_results", {}).get("limit", 1000)
            },
            "forbidden_patterns_count": len(self.rules.get("forbidden_queries", {}).get("patterns", [])),
            "sensitive_data_restrictions": len(self.rules.get("sensitive_data", {}).get("restrictions", []))
        }


# Global instance
_rules_service = BusinessRulesService()


def get_rules_service() -> BusinessRulesService:
    """Get the global business rules service instance."""
    return _rules_service
