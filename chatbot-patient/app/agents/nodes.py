"""LangGraph node functions for the patient agent.

    gate ─┬─ answered ─▶ END                       (a pending confirmation was resolved)
          └─ route    ─▶ router ─┬─ chat/clarify/refuse ─▶ END
                                 └─ use_tool ─▶ collect ─┬─ missing      ─▶ END
                                                         ├─ need_confirm ─▶ END
                                                         └─ execute ─▶ present ─▶ END

Safety-relevant behaviour lives here and in ``app/infrastructure/tools.py``:
identity is never read from the message, emergencies short-circuit everything, and
writes require an explicit confirmation turn.
"""
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.agents import llm
from app.agents.prompt_loader import loader
from app.infrastructure import tools
from app.infrastructure.tools import ToolError

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"chat", "clarify", "refuse", "use_tool"}

# Deterministic emergency screen. The prompt also covers this, but a model is the wrong
# single point of failure for "patient says they have chest pain", so we check in code
# first and never let the turn reach a tool.
_EMERGENCY_PATTERNS = [
    r"\bchest pain\b", r"\bcan'?t breathe\b", r"\bcannot breathe\b",
    r"\btrouble breathing\b", r"\bdifficulty breathing\b", r"\bshort(ness)? of breath\b",
    r"\bsevere bleeding\b", r"\bbleeding heavily\b", r"\bunconscious\b",
    r"\bpassed out\b", r"\bstroke\b", r"\bheart attack\b", r"\boverdose\b",
    r"\bsuicidal\b", r"\bkill myself\b", r"\bend my life\b", r"\bself[- ]harm\b",
    r"\bemergency\b", r"\bcall 911\b", r"\bambulance\b",
]

_EMERGENCY_REPLY = (
    "This sounds like it could be an emergency. Please call 911 now, or go straight to "
    "the Emergency Department at Block E (Mill Lane entrance) — it's open 24 hours.\n\n"
    "If someone is with you, ask them to help you get there. I'm not able to give medical "
    "help myself, and I don't want to delay you."
)


def _has_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in (text or ""))


def is_emergency(message: str) -> bool:
    text = (message or "").lower()
    return any(re.search(p, text) for p in _EMERGENCY_PATTERNS)


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------

def _pretty_date(value: Optional[str]) -> str:
    if not value:
        return "(date not set)"
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%A %-d %B")
    except (ValueError, TypeError):
        try:                                   # %-d is not portable to Windows
            return date.fromisoformat(str(value)[:10]).strftime("%A %d %B").replace(" 0", " ")
        except (ValueError, TypeError):
            return str(value)


def _pretty_time(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.strptime(str(value)[:5], "%H:%M")
        hour = parsed.hour % 12 or 12
        suffix = "am" if parsed.hour < 12 else "pm"
        return f"{hour}:{parsed.minute:02d}{suffix}"
    except ValueError:
        return str(value)


def _format_conversation(conversation: Optional[List[Dict[str, str]]]) -> str:
    turns = (conversation or [])[-8:]
    if not turns:
        return "(no prior messages)"
    return "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')}" for t in turns)


def _lang_name(state: Dict) -> str:
    return "Arabic" if (state.get("language") or "en").lower().startswith("ar") else "English"


def _prompt_vars(state: Dict, **extra) -> Dict[str, Any]:
    today = date.today()
    base = {
        "patient_name": state.get("patient_name") or "the patient",
        "today": f"{today.isoformat()} ({today.strftime('%A')})",
        "language": _lang_name(state),
        "conversation": _format_conversation(state.get("conversation")),
        "message": state.get("user_message", ""),
        "tool_catalog": tools.catalog(),
        "pending": (state.get("pending") or {}).get("description", "(nothing pending)"),
    }
    base.update(extra)
    return base


# Claims that a booking change has ALREADY happened. Only a turn that actually called
# the scheduler (action == "use_tool") is allowed to say this. The model will otherwise
# occasionally announce a cancellation it never performed, which is the single most
# damaging thing this bot could do, so it is caught in code rather than left to a prompt.
_COMPLETION_CLAIM = re.compile(
    r"\b("
    r"(has|have|had|is|are|was|were)\s+(now\s+|successfully\s+)?(been\s+)?"
    r"(cancell?ed|booked|rebooked|rescheduled)"
    r"|i(?:'ve| have)\s+(now\s+|successfully\s+)?(cancell?ed|booked|rebooked|rescheduled)"
    r"|(cancellation|booking)\s+(is|has been)\s+(complete|confirmed|done)"
    r")\b",
    re.IGNORECASE,
)

_UNVERIFIED_CLAIM_REPLY = (
    "Sorry — I need to check that properly before I say anything is done. "
    "Could you tell me again which appointment you mean, and I'll confirm it with you "
    "before making any change?"
)


def _guard_completion_claim(text: str, action: str) -> str:
    """Never let a non-executing turn claim a booking change was made."""
    if action == "use_tool" or not text:
        return text
    if _COMPLETION_CLAIM.search(text):
        logger.warning("suppressed false completion claim on a %r turn: %.160s", action, text)
        return _UNVERIFIED_CLAIM_REPLY
    return text


def _reply(state: Dict, text: str, action: str, *, service: Optional[str] = None,
           data: Optional[Dict] = None) -> Dict:
    state["final"] = {"text": _guard_completion_claim(text, action), "html": None,
                      "data_json": data, "action": action, "service": service}
    return state


# --------------------------------------------------------------------------
# gate: resolve a pending confirmation before anything else
# --------------------------------------------------------------------------

def gate_node(state: Dict) -> Dict:
    """If a write is awaiting confirmation, interpret this message as the answer."""
    if is_emergency(state.get("user_message", "")):
        logger.info("emergency pattern matched; short-circuiting turn")
        state["pending_cleared"] = True
        return _reply(state, _EMERGENCY_REPLY, "refuse")

    pending = state.get("pending")
    if not pending:
        return state

    verdict = (llm.complete_json(
        loader.system("confirm", **_prompt_vars(state)), temperature=0.0, max_tokens=60,
    ) or {}).get("decision", "unclear")

    if verdict == "confirm":
        logger.info("confirmed pending %s", pending.get("operation"))
        state["operation"] = pending.get("operation")
        state["params"] = dict(pending.get("params") or {})
        state["pending_cleared"] = True
        return execute_node(state, confirmed=True)

    if verdict == "deny":
        state["pending_cleared"] = True
        return _reply(state, "No problem — I've left it as it was. Is there anything "
                             "else I can help you with?", "chat")

    # Anything else: drop the pending action and treat the message as a fresh request,
    # so the patient is never trapped in a confirmation loop.
    state["pending_cleared"] = True
    state["pending"] = None
    return state


def after_gate(state: Dict) -> str:
    return "answered" if state.get("final") else "route"


# --------------------------------------------------------------------------
# router
# --------------------------------------------------------------------------

def router_node(state: Dict) -> Dict:
    # Generous token budget: the router emits params + reply + reason as one JSON object,
    # and a truncated object parses as nothing, which silently degrades every turn in a
    # long conversation to "sorry, I didn't catch that".
    decision = llm.complete_json(
        loader.system("router", **_prompt_vars(state)), temperature=0.0, max_tokens=900,
    ) or {}

    action = str(decision.get("action") or "").strip()
    if action not in _VALID_ACTIONS:
        logger.warning("router returned invalid action %r; falling back to clarify", action)
        action = "clarify"
        decision["reply"] = decision.get("reply") or (
            "Sorry, I didn't quite catch that. Could you tell me a little more about what "
            "you need?")

    operation = decision.get("operation")
    if action == "use_tool":
        available = tools.active_operations()
        if operation not in available:
            logger.warning("router chose unavailable operation %r", operation)
            action = "clarify"
            decision["reply"] = (
                "Sorry, I can't help with that one. I can look up your appointments, your "
                "own health record, or general hospital information — which would you like?")

    decision["action"] = action
    state["decision"] = decision
    state["operation"] = operation if action == "use_tool" else None
    state["params"] = dict(decision.get("params") or {})
    logger.info("router: action=%s operation=%s reason=%s",
                action, state.get("operation"), decision.get("reason"))

    if action in ("chat", "clarify", "refuse"):
        text = (decision.get("reply") or "").strip() or "How can I help?"
        return _reply(state, text, action)
    return state


def route_decision(state: Dict) -> str:
    return "use_tool" if (state.get("decision") or {}).get("action") == "use_tool" else "answered"


# --------------------------------------------------------------------------
# collect
# --------------------------------------------------------------------------

def collect_node(state: Dict) -> Dict:
    """Fill in the operation's parameters, then decide whether it needs confirming."""
    operation = state.get("operation")
    op = tools.active_operations().get(operation)
    if op is None:                       # router already validated; belt and braces
        return _reply(state, "Sorry, I can't do that right now.", "clarify")

    draft = {k: v for k, v in (state.get("params") or {}).items() if k in op.params}

    # Only ask the collector when there is something left to work out.
    if op.params and set(op.params) - set(draft):
        filled = llm.complete_json(
            loader.system("collect", **_prompt_vars(
                state, operation=op.name, params=", ".join(op.params),
                draft=json.dumps(draft, ensure_ascii=False))),
            temperature=0.0, max_tokens=300,
        ) or {}
        params = {k: v for k, v in (filled.get("params") or {}).items()
                  if k in op.params and v is not None}
        draft = {**params, **draft} if draft else params
        missing = [m for m in (filled.get("missing") or []) if isinstance(m, str)]
    else:
        missing = []

    # Identity can never come from the model. Strip it here as well as in tools.call,
    # so a stray value never even reaches the client.
    for forbidden in ("patient_id", "patient_name", "mrn", "patient_mrn"):
        if draft.pop(forbidden, None) is not None:
            logger.warning("collector supplied %r for %s; ignored", forbidden, op.name)

    if op.name == "appointments_book":
        draft, missing = _resolve_slot(state, draft, missing)
    elif op.name == "appointments_cancel":
        draft, missing = _resolve_appointment(state, draft, missing)

    state["params"] = draft
    state["missing"] = missing

    if missing:
        # The router's reply is only usable here if it is actually a question — it often
        # narrates the intended action instead ("I will cancel your 11am appointment"),
        # which would leave the patient thinking something happened.
        router_reply = ((state.get("decision") or {}).get("reply") or "").strip()
        question = router_reply if router_reply.endswith("?") else (
            f"Could you tell me {missing[0].replace('_', ' ')}?")
        return _reply(state, question, "clarify")

    if op.writes:
        return _stage_confirmation(state, op)
    return state


def after_collect(state: Dict) -> str:
    if state.get("final"):
        return "answered"
    return "execute"


_ORDINALS = [
    (1, (r"\bfirst\b", r"\b1st\b", r"\bearliest\b")),
    (2, (r"\bsecond\b", r"\b2nd\b")),
    (3, (r"\bthird\b", r"\b3rd\b")),
    (4, (r"\bfourth\b", r"\b4th\b")),
    (5, (r"\bfifth\b", r"\b5th\b")),
]


def _resolve_slot(state: Dict, draft: Dict[str, Any],
                  missing: List[str]) -> tuple[Dict[str, Any], List[str]]:
    """Pin a booking to a slot the scheduler actually offered.

    The model reliably gets provider display names and slot ids confused (it will happily
    pass "Dr. Priya Nair" as provider_id). Rather than trusting it, we match its date/time
    — or an ordinal like "the first one" — against the slots from the last search and take
    provider_id/date/time from that record.
    """
    slots = state.get("last_slots") or []
    if not slots:
        return draft, missing

    def adopt(slot: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(draft)
        merged["provider_id"] = slot.get("provider_id")
        merged["date"] = slot.get("date")
        merged["time"] = slot.get("time")
        return merged

    date_value, time_value = draft.get("date"), draft.get("time")

    # 1. exact date + time
    if date_value and time_value:
        for slot in slots:
            if slot.get("date") == date_value and str(slot.get("time"))[:5] == str(time_value)[:5]:
                return adopt(slot), [m for m in missing if m in ("reason",)]

    # 2. ordinal reference in the patient's message ("the first one")
    message = (state.get("user_message") or "").lower()
    for index, patterns in _ORDINALS:
        if any(re.search(p, message) for p in patterns) and len(slots) >= index:
            return adopt(slots[index - 1]), [m for m in missing if m in ("reason",)]

    # 3. a time alone, when it is unambiguous across the offered slots
    if time_value and not date_value:
        matches = [s for s in slots if str(s.get("time"))[:5] == str(time_value)[:5]]
        if len(matches) == 1:
            return adopt(matches[0]), [m for m in missing if m in ("reason",)]

    # 4. provider_id that isn't one we offered — drop it rather than send it on
    offered = {s.get("provider_id") for s in slots}
    if draft.get("provider_id") and draft["provider_id"] not in offered:
        logger.info("dropping unrecognised provider_id %r (offered: %s)",
                    draft["provider_id"], sorted(o for o in offered if o))
        draft = {k: v for k, v in draft.items() if k != "provider_id"}
        if "provider_id" not in missing:
            missing = missing + ["which appointment time you'd like"]

    return draft, missing


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _times_in(message: str) -> set:
    """Clock times mentioned in a message, as 'HH:MM'.

    Only matches forms that are unambiguously a time — '11am', '9:30', '14:00' — so that
    a date like 'Monday 10 August' does not read as 10 o'clock.
    """
    found = set()
    for match in re.finditer(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", message):
        hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if 0 <= hour < 24 and 0 <= minute < 60:
            found.add(f"{hour:02d}:{minute:02d}")
    for match in re.finditer(r"\b(\d{1,2})\s*(am|pm)\b", message):
        hour, meridiem = int(match.group(1)), match.group(2)
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if 0 <= hour < 24:
            found.add(f"{hour:02d}:00")
    return found


def _weekdays_in(message: str) -> set:
    return {i for i, name in enumerate(_WEEKDAYS) if re.search(rf"\b{name}\b", message)}


def _weekday_of(value: Optional[str]) -> int:
    try:
        return date.fromisoformat(str(value)[:10]).weekday()
    except (ValueError, TypeError):
        return -1


def _known_appointments(state: Dict) -> List[Dict[str, Any]]:
    """The patient's upcoming appointments — from session memory, or fetched if absent."""
    known = state.get("last_appointments")
    if known:
        return known
    if state.get("patient_id") is None:
        return []
    try:
        data = tools.call("appointments_list", {"include_past": False},
                          patient_id=state["patient_id"],
                          patient_mrn=state.get("patient_mrn"))
    except ToolError:
        return []
    upcoming = data.get("upcoming") or []
    state["appts_out"] = upcoming
    state["last_appointments"] = upcoming
    return upcoming


def _resolve_appointment(state: Dict, draft: Dict[str, Any],
                         missing: List[str]) -> tuple[Dict[str, Any], List[str]]:
    """Pin a cancellation to one of the patient's real appointments.

    The model tends to pass the position in the list it just printed ("1") as appt_id.
    Match against the actual rows instead: by real id, by ordinal, or by date.
    """
    appts = _known_appointments(state)
    if not appts:
        return draft, missing

    valid = {str(a.get("appt_id")) for a in appts}
    requested = draft.get("appt_id")

    if requested is not None and str(requested) in valid:
        return draft, [m for m in missing if m == "reason"]

    message = (state.get("user_message") or "").lower()

    # "the first one" / "the second appointment"
    for index, patterns in _ORDINALS:
        if any(re.search(p, message) for p in patterns) and len(appts) >= index:
            draft = {**draft, "appt_id": appts[index - 1].get("appt_id")}
            return draft, [m for m in missing if m == "reason"]

    # Only one upcoming appointment, and they clearly mean that one.
    if len(appts) == 1:
        draft = {**draft, "appt_id": appts[0].get("appt_id")}
        return draft, [m for m in missing if m == "reason"]

    # Narrow by any time and/or weekday they mentioned ("my 11am one on Monday").
    candidates = appts
    times = _times_in(message)
    if times:
        candidates = [a for a in candidates if str(a.get("time"))[:5] in times] or candidates
    weekdays = _weekdays_in(message)
    if weekdays:
        narrowed = [a for a in candidates if _weekday_of(a.get("date")) in weekdays]
        candidates = narrowed or candidates
    iso = [a for a in candidates if a.get("date") and str(a["date"]) in message]
    if len(iso) == 1:
        candidates = iso

    if len(candidates) == 1 and candidates is not appts:
        draft = {**draft, "appt_id": candidates[0].get("appt_id")}
        return draft, [m for m in missing if m == "reason"]

    logger.info("could not resolve appt_id %r against %s", requested, sorted(valid))
    draft = {k: v for k, v in draft.items() if k != "appt_id"}
    return draft, missing + ["which appointment you'd like to cancel"]


def _describe_pending(state: Dict, op, params: Dict[str, Any]) -> str:
    """A sentence the patient can actually check before saying yes."""
    if op.name == "appointments_book":
        provider = _provider_name(state, params.get("provider_id")) or "the clinic"
        when = f"{_pretty_date(params.get('date'))} at {_pretty_time(params.get('time'))}"
        return f"book an appointment with {provider} on {when}"
    if op.name == "appointments_cancel":
        appt = _find_appointment(state, params.get("appt_id"))
        if appt:
            return (f"cancel your appointment with {appt.get('provider')} on "
                    f"{_pretty_date(appt.get('date'))} at {_pretty_time(appt.get('time'))}")
        return "cancel that appointment"
    return f"run {op.name}"


def _provider_name(state: Dict, provider_id: Optional[str]) -> Optional[str]:
    """Provider display name for the slot being booked, from the last search results."""
    if not provider_id:
        return None
    for slot in state.get("last_slots") or []:
        if slot.get("provider_id") == provider_id:
            return slot.get("provider")
    return None


def _find_appointment(state: Dict, appt_id) -> Optional[Dict]:
    """Look up one of the patient's own appointments so a cancellation can be described."""
    if appt_id is None:
        return None
    for appt in _known_appointments(state):
        if str(appt.get("appt_id")) == str(appt_id):
            return appt
    return None


def _stage_confirmation(state: Dict, op) -> Dict:
    description = _describe_pending(state, op, state.get("params") or {})
    state["pending_out"] = {
        "operation": op.name,
        "params": state.get("params") or {},
        "description": description,
    }
    return _reply(state, f"Just to confirm — you'd like me to {description}? "
                         f"Reply 'yes' and I'll do it.", "confirm", service=op.service)


# --------------------------------------------------------------------------
# execute
# --------------------------------------------------------------------------

def execute_node(state: Dict, *, confirmed: bool = False) -> Dict:
    operation = state.get("operation")
    op = tools.OPERATIONS.get(operation)
    try:
        result = tools.call(
            operation, state.get("params") or {},
            patient_id=state.get("patient_id"),
            patient_mrn=state.get("patient_mrn"),
            confirmed=confirmed,
        )
    except ToolError as exc:
        logger.info("tool %s failed: %s", operation, exc)
        state["tool_error"] = str(exc)
        return _reply(state, str(exc), "error", service=op.service if op else None)
    except Exception:
        logger.exception("unexpected tool failure for %s", operation)
        return _reply(state, "Sorry — something went wrong on our side. Please try again "
                             "in a moment.", "error", service=op.service if op else None)

    state["result"] = result
    # Remember what the scheduler offered, so a follow-up booking resolves against real
    # slots instead of the model's recollection of the prose we printed.
    if operation == "appointments_search":
        state["slots_out"] = (result.get("slots") or [])[:10]
    elif operation == "appointments_list":
        state["appts_out"] = result.get("upcoming") or []
    return present_node(state)


# --------------------------------------------------------------------------
# present
# --------------------------------------------------------------------------

def present_prompt(state: Dict) -> str:
    """The presentation prompt, exposed so the SSE endpoint can stream the same call."""
    result = state.get("result") or {}
    return loader.system("present", **_prompt_vars(
        state, operation=state.get("operation"),
        result=json.dumps(result, ensure_ascii=False)[:6000]))


def present_node(state: Dict) -> Dict:
    operation = state.get("operation")
    op = tools.OPERATIONS.get(operation)
    result = state.get("result") or {}

    text = llm.complete(present_prompt(state), temperature=0.3,
                        max_tokens=600, model=llm.ANSWER_MODEL).strip()

    if not text:
        text = _fallback_text(operation, result)

    return _reply(state, text, "use_tool",
                  service=op.service if op else None, data=result)


def _fallback_text(operation: Optional[str], result: Dict) -> str:
    """Deterministic wording if the answering model returns nothing, so a tool call
    never surfaces as an empty message."""
    if operation == "appointments_book" and result.get("message"):
        return str(result["message"])
    if operation == "appointments_cancel" and result.get("message"):
        return str(result["message"])
    if operation == "appointments_list":
        upcoming = result.get("upcoming") or []
        if not upcoming:
            return "You don't have any upcoming appointments booked at the moment."
        lines = [f"- {a.get('provider')} on {_pretty_date(a.get('date'))} at "
                 f"{_pretty_time(a.get('time'))}" for a in upcoming]
        return "Here are your upcoming appointments:\n" + "\n".join(lines)
    if operation == "appointments_search":
        slots = result.get("slots") or []
        if not slots:
            return "I couldn't find any open slots in that period."
        lines = [f"- {s.get('provider')} on {_pretty_date(s.get('date'))} at "
                 f"{_pretty_time(s.get('time'))}" for s in slots[:5]]
        return "Here are some available times:\n" + "\n".join(lines)
    if operation == "hospital_info":
        topics = result.get("topics") or []
        return str(topics[0].get("summary")) if topics else "I don't have that on file."
    return "Here's what I found."
