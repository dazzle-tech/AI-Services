# medai_crewai_crew.py
import os
from typing import Optional
from crewai import Agent, Task, Crew, Process, LLM
from app.core.config import settings
from app.crewai.tools import SQLGenTool, ValidatorTool, FormatterTool

# Use OpenAI as the LLM provider for CrewAI
# Configure based on settings
if settings.llm_provider == "openai":
    llm = LLM(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.2,
    )
else:
    # Fallback to Ollama if OpenAI is not configured
    LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3:8b")
    llm = LLM(
        model=f"ollama/{LLAMA_MODEL}",
        temperature=0.2,
    )

# Shared tools that talk to your FastAPI microservices
sql_tool = SQLGenTool()
validator_tool = ValidatorTool()
formatter_tool = FormatterTool()

# Agent 1: planner / triage
planner_agent = Agent(
    role="Triage Planner",
    goal=(
        "Decide if the doctor's message is a casual chat or a data request. "
        "For data requests, rewrite it into a clear, SQL-ready question using patient IDs if given."
    ),
    backstory=(
        "You are an experienced hospital informatics specialist who knows "
        "how doctors phrase questions and how they map to database queries."
    ),
    llm=llm,
    allow_delegation=False,
)

# Agent 2: DB agent that actually uses the tools
db_agent = Agent(
    role="Hospital Data Agent",
    goal=(
        "Answer hospital data questions strictly from hospital.db using "
        "the SQL generator, validator, and formatter tools. Always provide "
        "detailed, human-readable summaries that include patient names and key information, "
        "not just record counts."
    ),
    backstory=(
        "You are a cautious data assistant. You never invent values and "
        "always respect role-based access and patient privacy. When formatting results, "
        "you ensure summaries are informative and include patient names, dates, and relevant details."
    ),
    tools=[sql_tool, validator_tool, formatter_tool],
    llm=llm,
    allow_delegation=False,
)

def build_medai_crew(
    user_message: str, 
    user_id: str, 
    enhanced_query: Optional[str] = None,
    entities: Optional[dict] = None,
    is_specific: bool = False
) -> Crew:
    """
    Build a CrewAI pipeline for a single user message.

    - planner_agent: decides if it's data or just chat, and if data,
      rewrites the question clearly.
    - db_agent: uses the SQL generator, validator, and formatter tools
      to actually query hospital.db and summarize the results.

    Args:
        user_message: Original user message
        user_id: User ID
        enhanced_query: Enhanced query with context (optional)
        entities: Extracted entities (optional)
        is_specific: Whether query is about a specific patient (optional)

    Returns:
        Crew instance ready to execute
    """
    # Build context string for the planner
    context_parts = [f"User message: {user_message}"]
    
    if enhanced_query:
        context_parts.append(f"\nEnhanced context: {enhanced_query}")
    
    if entities:
        import json
        context_parts.append(f"\nExtracted entities: {json.dumps(entities, ensure_ascii=False)}")
    
    if is_specific:
        context_parts.append("\n⚠️ IMPORTANT: This query is about a SPECIFIC patient. Use patient_id if provided in entities.")
    else:
        context_parts.append("\n⚠️ IMPORTANT: This is a GENERAL query (not about a specific patient). Do NOT restrict by patient_id.")
    
    context = "\n".join(context_parts)
    
    # Task 1: planner decides how to phrase the DB question
    plan_task = Task(
        description=(
            f"{context}\n\n"
            "If this is NOT a data question (for example, a casual greeting), "
            "just answer the user directly and STOP.\n"
            "If it IS a data question, return ONLY a short, clear text "
            "that describes the data to fetch (who/what/when) in one paragraph. "
            "Use patient IDs if they are provided in the entities."
        ),
        agent=planner_agent,
        expected_output="A clear, concise text description of what data to fetch from the database, or a direct answer if it's not a data question.",
    )

    # Task 2: db_agent uses tools to actually hit DB
    db_task = Task(
        description=(
            "Using the planner's clarified question, do the following:\n"
            "1. Call sql_generator to get SQL (pass the clarified question as 'text' and the user_id).\n"
            "2. Call sql_validator with that SQL and the same user_id.\n"
            "3. If validation is not allowed or fails, respond with a short explanation.\n"
            "4. If valid, call result_formatter with:\n"
            "   - user_intent = the original user question (e.g., 'who was that patient'),\n"
            "   - rows = the rows from the validator,\n"
            "   - columns = the columns from the validator if provided.\n"
            "5. IMPORTANT: The result_formatter will return a dictionary with 'summary' and 'json' fields.\n"
            "   - Use the 'summary' field as your final text response (it's human-readable)\n"
            "   - Use the 'json' field as your 'data_json' (it contains the table structure)\n"
            "6. Return a dictionary with keys: 'summary' (the formatter's summary text), 'data_json' (the formatter's 'json' field), "
            "and 'sql' (the SQL you executed or attempted).\n"
            "7. CRITICAL: For questions like 'who was that patient', make sure the summary includes the patient's name and key details, not just a count."
        ),
        agent=db_agent,
        tools=[sql_tool, validator_tool, formatter_tool],
        expected_output="A dictionary with 'summary' (human-readable text describing the results with patient names/details when relevant), 'data_json' (formatted data with table structure), and 'sql' (the executed SQL query).",
    )

    crew = Crew(
        agents=[planner_agent, db_agent],
        tasks=[plan_task, db_task],
        process=Process.sequential,
    )
    return crew
