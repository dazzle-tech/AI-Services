"""LangGraph state graph for the patient agent.

    gate ─┬─ answered ─▶ END
          └─ route    ─▶ router ─┬─ answered ─▶ END
                                 └─ use_tool ─▶ collect ─┬─ answered ─▶ END
                                                         └─ execute ─▶ present ─▶ END
"""
import logging
from typing import Dict, List, Optional

from langgraph.graph import END, StateGraph

from app.agents import nodes
from app.agents.state import PatientAgentState

logger = logging.getLogger(__name__)

_graph = None


def build_graph():
    g = StateGraph(PatientAgentState)
    g.add_node("gate", nodes.gate_node)
    g.add_node("router", nodes.router_node)
    g.add_node("collect", nodes.collect_node)
    g.add_node("execute", nodes.execute_node)
    g.set_entry_point("gate")
    g.add_conditional_edges("gate", nodes.after_gate, {"answered": END, "route": "router"})
    g.add_conditional_edges("router", nodes.route_decision,
                            {"answered": END, "use_tool": "collect"})
    # execute_node calls present_node itself so the same path serves the confirmation
    # replay in gate_node, which re-enters execution without traversing the graph.
    g.add_conditional_edges("collect", nodes.after_collect,
                            {"answered": END, "execute": "execute"})
    g.add_edge("execute", END)
    return g.compile()


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_turn(
    user_message: str,
    *,
    patient_id: Optional[int],
    patient_mrn: Optional[str] = None,
    patient_name: Optional[str] = None,
    conversation: Optional[List[Dict[str, str]]] = None,
    session_id: str = "default",
    pending: Optional[Dict] = None,
    last_slots: Optional[List[Dict]] = None,
    last_appointments: Optional[List[Dict]] = None,
) -> Dict:
    """Run one conversational turn.

    ``patient_id`` is the authenticated identity from the session. It is placed into the
    state here and is the ONLY source of identity for the whole turn — nothing
    downstream reads a patient id out of the message.
    """
    state: Dict = {
        "user_message": user_message,
        "conversation": conversation or [],
        "session_id": session_id,
        # Reply in the language of the message itself, like the clinician bot.
        "language": "ar" if nodes._has_arabic(user_message) else "en",
        "patient_id": patient_id,
        "patient_mrn": patient_mrn,
        "patient_name": patient_name,
        "pending": pending,
        "last_slots": last_slots or [],
        "last_appointments": last_appointments or [],
    }
    try:
        result = get_graph().invoke(state)
    except Exception as exc:
        logger.exception("patient agent graph failed")
        return {
            "text": "Sorry — I hit a problem just then. Please try again in a moment.",
            "html": None, "data_json": None, "action": "error", "service": None,
            "_pending": None, "_pending_cleared": False,
        }

    final = result.get("final") or {
        "text": "How can I help?", "html": None, "data_json": None,
        "action": "chat", "service": None,
    }
    # Surface confirmation bookkeeping for the route handler to persist on the session.
    final["_pending"] = result.get("pending_out")
    final["_pending_cleared"] = bool(result.get("pending_cleared"))
    final["_slots"] = result.get("slots_out")
    final["_appts"] = result.get("appts_out")
    return final
