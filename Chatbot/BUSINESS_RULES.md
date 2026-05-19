# Business Rules and Restrictions

This document describes the business rules and restrictions enforced by the MedAI Assistant chatbot to prevent queries that would return too many results or violate data access policies.

## Overview

The business rules service (`app/services/rules.py`) validates user queries before execution and checks result counts after execution to ensure queries comply with system limitations and best practices.

## Rules Configuration

Rules can be configured in `data/rules.json` or by modifying the default rules in `app/services/rules.py`.

## Active Rules

### 1. Maximum Results Limit

**Purpose**: Prevents queries from returning excessive amounts of data.

- **Limit**: 1000 rows (configurable)
- **Message**: "This query would return too many results. Please refine your query with specific criteria (e.g., date range, patient name, or other filters)."

**Example Blocked Query**:
- A query that would return 5000 patient records

### 2. Data Modification Restrictions

**Purpose**: Prevents any data modification operations (read-only system).

**Blocked Operations**:
- DELETE, UPDATE, INSERT, DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE, EXEC, EXECUTE, CALL

**Example Blocked Queries**:
- "Delete patient record"
- "Update patient information"
- "Insert new patient"
- SQL: `DELETE FROM ap_patient WHERE id = 1`

**Message**: "Data modification operations (DELETE, UPDATE, INSERT, DROP, etc.) are not allowed. This system is read-only for data queries."

### 3. Forbidden Query Patterns

**Purpose**: Blocks queries that explicitly request all patients or would return all records.

**Blocked Patterns**:
- "all patients" / "every patient" / "entire patients"
- "show all patients" / "show me all patients"
- "list all patients" / "list patients"
- "get all patients" / "get every patient"
- "count all patients" / "count every patient"
- SQL: `SELECT * FROM ap_patient WHERE 1=1` (or without WHERE clause)

**Example Blocked Queries**:
- "Show me all patients"
- "List all patients in the hospital"
- "Get every patient"
- "Count all patients"

**Allowed Queries** (with filters):
- "Show me all patients admitted this week"
- "List patients in Ward A"
- "Get all patients discharged in January 2024"

### 4. Required Filters

**Purpose**: Ensures general queries include at least one filter to narrow results.

**Required Filters for Patient Queries**:
- Date range (e.g., "this week", "last month", "in January")
- Patient name or ID
- Status (e.g., "admitted", "discharged")
- Ward or room number
- Department or other criteria

**Example**:
- ❌ Blocked: "Show me all patients"
- ✅ Allowed: "Show me all patients admitted this week"
- ✅ Allowed: "List patients in Ward 3"

### 5. Date Range Limits

**Purpose**: (Optional) Prevents queries with excessively large date ranges.

**Status**: Disabled by default (see `data/rules.json`).

**Example**:
- ❌ Blocked: "Show me all patients from the last 5 years"
- ✅ Allowed: "Show me all patients from the last 6 months"

### 6. Sensitive Data Restrictions

**Purpose**: Blocks queries requesting sensitive financial or identification information.

**Blocked Patterns**:
- SSN / Social Security Number
- Credit card information
- Bank account information
- Passwords / PINs
- PII (Personally Identifiable Information)

**Example Blocked Queries**:
- "What is the patient's SSN?"
- "Show me credit card numbers"
- "Get bank account information"
- "What is the password?"

### 7. Bulk Operations Restrictions

**Purpose**: Prevents bulk data export or download operations.

**Blocked Patterns**:
- "export all data" / "download all patients"
- "dump records" / "extract all information"
- "export patient data" / "download records"

**Example Blocked Queries**:
- "Export all patient data"
- "Download all records"
- "Dump all encounters"

**Message**: "Bulk data export is not available. Please query specific information with appropriate filters."

### 8. Future Date Restrictions

**Purpose**: (Optional) Prevents queries for future dates (data doesn't exist yet).

**Status**: Disabled by default (see `data/rules.json`).

**Blocked Patterns**:
- "tomorrow", "next week", "next month", "next year"
- "future", "upcoming"
- Years in the future (2025, 2026, etc.)

**Example Blocked Queries**:
- "Show me patients admitted tomorrow"
- "List appointments next week"
- "Get data for 2025"

**Message**: "I cannot query data for future dates. Please specify a date in the past or present."

### 9. Historical Data Limits

**Purpose**: (Optional) Prevents queries for very old data (beyond retention period).

**Status**: Disabled by default (see `data/rules.json`).

**Example Blocked Queries**:
- "Show me patients from 2010"
- "Get data from 2005"
- "List records from 15 years ago"

### 10. SQL Query Restrictions

**Purpose**: Prevents dangerous or inefficient SQL patterns.

**Restricted Patterns**:
- `SELECT * FROM table` without WHERE clause
- Queries with more than 3 JOINs
- `COUNT(*)` without WHERE clause
- `UNION ALL` without LIMIT
- Queries without WHERE clause (unless simple SELECT with LIMIT)

**Example Blocked SQL**:
- `SELECT * FROM ap_patient` (no WHERE)
- `SELECT * FROM ap_encounter WHERE 1=1` (fake WHERE)
- `SELECT COUNT(*) FROM ap_patient` (no WHERE)

**Message**: "This SQL query contains restricted operations or patterns that are not allowed."

### 11. Performance Restrictions

**Purpose**: Prevents queries that may cause performance issues.

**Limits**:
- Maximum 3 JOINs per query
- Maximum 2 subqueries per query
- WHERE clause required (with exceptions for simple SELECT with LIMIT)

**Example Blocked Queries**:
- Queries with 4+ JOINs
- Queries with 3+ subqueries
- Queries without WHERE clause

**Message**: "This query may be too complex or resource-intensive. Please simplify your query or add more specific filters."

### 12. Aggregate Query Restrictions

**Purpose**: Limits the number of aggregate functions in a single query.

- **Maximum Aggregate Functions**: 5 (COUNT, SUM, AVG, MAX, MIN, etc.)

**Example Blocked Query**:
- A query with 6+ aggregate functions

**Message**: "This query has too many aggregate functions. Please simplify your query."

### 13. Text Search Restrictions

**Purpose**: Helps prevent overly broad text searches from impacting performance.

**Requirements**:
- LIMIT is recommended for text search queries (LIKE/ILIKE), but not required
- Other safety rails still apply (timeouts and max-results)

**Example Blocked Query**:
- None (LIMIT is not enforced for text search)

**Message**: "Text search queries may be large. Consider adding LIMIT clauses and reasonable search terms to prevent performance issues."

### 14. Column Restrictions

**Purpose**: Blocks access to sensitive columns.

**Forbidden Columns**:
- password, passwd, secret, token, api_key

**Example Blocked Query**:
- `SELECT password FROM users`

**Message**: "Access to certain sensitive columns is restricted."

### 15. Extended Forbidden Patterns

**Additional blocked patterns for other entities**:
- "show all encounters" / "list all encounters"
- "get all diagnoses" / "find all treatments"
- "show all doctors" / "list all staff"
- "get all wards" / "list all departments"

**Message**: "I cannot return all records without filters. Please specify a date range, patient, or other criteria to narrow down your query."

## How Rules Are Applied

### Query Validation Flow

1. **Pre-Query Validation**: Rules are checked after intent detection and entity extraction, but before SQL generation.
2. **SQL Validation**: After SQL is generated, rules are checked again on the SQL query itself.
3. **Result Validation**: After query execution, result count is checked against the maximum limit.

### Rule Enforcement Points

1. **Natural Language Query**: Patterns in the user's message are checked.
2. **SQL Query**: Generated SQL queries are validated for forbidden patterns.
3. **Result Count**: Number of returned rows is validated against the limit.

## Customization

### Modifying Rules

You can modify rules in two ways:

1. **Edit `data/rules.json`**: Update the JSON configuration file (requires service restart).
2. **Edit `app/services/rules.py`**: Modify the `_get_default_rules()` method for code-based rules.

### Adding New Rules

To add a new rule pattern:

1. Add a new pattern to `forbidden_queries.patterns` in `rules.json`:
```json
{
  "pattern": "\\byour\\s+pattern\\b",
  "case_sensitive": false,
  "message": "Your custom error message here."
}
```

2. Or modify `app/services/rules.py` to add the pattern programmatically.

### Disabling Rules

To disable a rule category, set `"enabled": false` in the rule configuration:

```json
{
  "forbidden_queries": {
    "enabled": false,
    "patterns": [...]
  }
}
```

## Examples

### Blocked Queries

```
User: "Show me all patients"
Response: "I cannot return all patients in the hospital as this would be too many results. Please specify a date range, patient name, or other criteria to narrow down your query."

User: "List every patient"
Response: "I cannot return all patients in the hospital as this would be too many results. Please specify a date range, patient name, or other criteria to narrow down your query."

User: "Get all patients from the last 10 years"
Response: "The requested date range is too large. Please limit your query to a maximum of 365 days."
```

### Allowed Queries

```
User: "Show me all patients admitted this week"
✅ Allowed (has date filter)

User: "List patients in Ward 3"
✅ Allowed (has ward filter)

User: "How old is John Smith?"
✅ Allowed (specific patient query)

User: "Show me patients discharged in January 2024"
✅ Allowed (has date filter)
```

## Logging

Rule violations are logged with the `🚫` emoji prefix:

```
🚫 Query blocked by rule: \b(all|every|entire)\s+(patient|patients)\b
🚫 SQL query blocked by rule: select\s+\*\s+from\s+ap_patient
🚫 Result limit exceeded: 1500 > 1000
```

## Integration

The rules service is integrated into the chat orchestrator (`app/services/chat_orchestrator.py`) and is automatically applied to all data queries. No additional configuration is required for basic usage.

## Testing

To test rules:

1. Try a blocked query: "Show me all patients"
2. Try an allowed query with filters: "Show me all patients admitted this week"
3. Check logs for rule enforcement messages
