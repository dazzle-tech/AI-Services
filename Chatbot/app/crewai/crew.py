# medai_crewai_crew.py
import json
import logging
import os
from typing import Optional

from crewai import Agent, Task, Crew, Process, LLM
from app.core.config import settings
from app.crewai.tools import (
    SQLGenTool,
    ValidatorTool,
    FormatterTool,
    DraftPrescriptionTool,
    SubmitPrescriptionTool,
    get_tools_for_role,
)

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
    LLAMA_MODEL = os.getenv("LLAMA_MODEL", "") or os.getenv("OPENAI_MODEL", "")
    llm = LLM(
        model=f"ollama/{LLAMA_MODEL}",
        temperature=0.2,
    )

logger = logging.getLogger(__name__)

# Shared tools that talk to your FastAPI microservices
sql_tool = SQLGenTool()
validator_tool = ValidatorTool()
formatter_tool = FormatterTool()

# Advanced write tools
try:
    draft_prescription_tool = DraftPrescriptionTool()
    submit_prescription_tool = SubmitPrescriptionTool()
except Exception as e:
    logger.warning("⚠️ Failed to initialize prescription tools: %s", e)
    draft_prescription_tool = None
    submit_prescription_tool = None

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

# Agent 3: Prescription assistant (role-gated)
prescription_agent = Agent(
    role="Prescription Assistant",
    goal=(
        "Help clinical users draft and submit prescriptions safely. "
        "Only use prescription tools when the user explicitly requests a new order or prescription."
    ),
    backstory=(
        "You are a clinical prescription assistant. You never submit medications without explicit confirmation. "
        "If the user asks to draft a prescription, create a draft. If they want to submit, require a confirmation token."
    ),
    tools=[tool for tool in [draft_prescription_tool, submit_prescription_tool] if tool],
    llm=llm,
    allow_delegation=False,
)

def build_medai_crew(
    user_message: str,
    user_id: str,
    role: str,
    enhanced_query: Optional[str] = None,
    entities: Optional[dict] = None,
    is_specific: bool = False,
) -> Crew:
    """
    Build a CrewAI pipeline for a single user message.

    The crew uses role-aware tool availability and enforces confirmation for
    protected write actions.
    """
    context_parts = [f"User message: {user_message}"]
    if enhanced_query:
        context_parts.append(f"\nEnhanced context: {enhanced_query}")
    if entities:
        context_parts.append(f"\nExtracted entities: {json.dumps(entities, ensure_ascii=False)}")

    if is_specific:
        context_parts.append(
            "\n⚠️ IMPORTANT: This query is about a SPECIFIC patient. Use medical_record_number (MRN) if provided in entities."
        )
    else:
        context_parts.append(
            "\n⚠️ IMPORTANT: This is a GENERAL query (not about a specific patient). Do NOT restrict by MRN unless explicitly requested."
        )

    context = "\n".join(context_parts)

    plan_task = Task(
        description=(
            f"{context}\n\n"
            "If this is NOT a data question, just answer directly and STOP.\n"
            "If it IS a data question, rewrite it into a clear query that can be converted into SQL.\n"
            "If the user is requesting a prescription, route to the prescription tools with the required patient MRN and medication details."
        ),
        agent=planner_agent,
        expected_output=(
            "A clear decision whether this is a casual/chat question, a data query, or a prescription request. "
            "When appropriate, produce a concise target query for the database or a prescription drafting action."
        ),
    )

    tool_list = get_tools_for_role(role)

    # Build DB / write agent
    db_task = Task(
        description=(
            "When the planner decides this is a data request, use the SQL generator, validator, and formatter tools.\n"
            "When the planner decides this is a prescription draft request, use the draft_prescription tool.\n"
            "When the planner decides this is a prescription submit request, use the submit_prescription tool only if a confirmation token is provided.\n"
            "If a protected write action is detected, require an explicit confirmation token and do not execute without it."
        ),
        agent=db_agent,
        tools=[tool for tool in tool_list if tool],
        expected_output=(
            "A dictionary that either contains a formatted query result, a prescription draft, or a submission confirmation."
        ),
    )

    crew = Crew(
        agents=[planner_agent, db_agent],
        tasks=[plan_task, db_task],
        process=Process.sequential,
    )
    return crew
