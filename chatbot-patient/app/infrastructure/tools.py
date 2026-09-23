"""Tool registry and HTTP client for the patient agent.

The patient agent may call exactly the operations declared in ``OPERATIONS`` below, on
exactly the services listed in the ``[PATIENT]`` section of ``Services.txt``. Anything
the model asks for that isn't in this table is rejected before a request is made.

Two invariants live here, and they are the reason tool calls go through this module
rather than being assembled in the nodes:

1. ``patient_id`` is injected by :func:`call` from the authenticated session and
   OVERWRITES whatever the model put in the payload. A prompt injection that says
   "look up patient 1002" cannot change which record is fetched.
2. Write operations are marked ``writes=True`` and are refused unless the caller passes
   ``confirmed=True``, which only happens after the user has confirmed in conversation.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

# Aliased: this module already has a `catalog()` function (the operation list for the
# router prompt), which would otherwise shadow the imported module.
from medai_core.services import catalog as service_catalog
from medai_core.tools.registry import REGISTRY, ToolSpec

from app.core.config import settings

logger = logging.getLogger(__name__)


# Where each service lives comes from the one canonical map in medai_core, shared with
# the clinician bot — so a host or port is never defined twice. This bot restricts itself
# to the patient services; `active_operations()` narrows that further to what
# Services.txt [PATIENT] actually enables.
SERVICES: Dict[str, ToolSpec] = {
    name: REGISTRY[name]
    for name in ("AppointmentSchedulerService", "HospitalInfoService", "MyRecordService")
}


@dataclass(frozen=True)
class Operation:
    name: str                       # what the router selects
    service: str
    path: str
    description: str
    needs_patient: bool = False     # inject the session's patient_id
    writes: bool = False            # requires explicit user confirmation
    params: List[str] = field(default_factory=list)   # params the model may supply

    @property
    def spec(self) -> ToolSpec:
        return SERVICES[self.service]

    @property
    def url(self) -> str:
        return f"{self.spec.base_url}{self.path}"


OPERATIONS: Dict[str, Operation] = {
    "appointments_list": Operation(
        "appointments_list", "AppointmentSchedulerService", "/api/v1/appointments/list",
        "List the patient's own upcoming (and optionally past) appointments.",
        needs_patient=True, params=["include_past"],
    ),
    "appointments_search": Operation(
        "appointments_search", "AppointmentSchedulerService", "/api/v1/appointments/search",
        "Find open appointment slots, optionally filtered by department and date range.",
        params=["department", "date_from", "date_to", "limit"],
    ),
    "appointments_book": Operation(
        "appointments_book", "AppointmentSchedulerService", "/api/v1/appointments/book",
        "Book a specific open slot. Requires provider_id, date and time from a prior search.",
        needs_patient=True, writes=True, params=["provider_id", "date", "time", "reason"],
    ),
    "appointments_cancel": Operation(
        "appointments_cancel", "AppointmentSchedulerService", "/api/v1/appointments/cancel",
        "Cancel one of the patient's own appointments by appt_id.",
        needs_patient=True, writes=True, params=["appt_id", "reason"],
    ),
    "hospital_info": Operation(
        "hospital_info", "HospitalInfoService", "/api/v1/hospital-info/query",
        "Answer a general, non-clinical question about the hospital: visiting hours, "
        "parking, location, departments, contact numbers, pharmacy, billing.",
        params=["question"],
    ),
    "my_record": Operation(
        "my_record", "MyRecordService", "/api/v1/my-record",
        "Read the patient's own record. Sections: profile, allergies, conditions, "
        "medications, labs, visits, vitals.",
        needs_patient=True, params=["sections", "lab_limit"],
    ),
}


class ToolError(Exception):
    """A tool call could not be completed. The message is safe to show a patient."""


def load_patient_services() -> List[str]:
    """Service names from the [PATIENT] section of Services.txt.

    Parsing is shared with the clinician bot (medai_core), so both read the file the
    same way — but this bot only ever asks for the [PATIENT] section.
    """
    return service_catalog.load_patient_services(settings.services_path)


def active_operations() -> Dict[str, Operation]:
    """Operations whose service is listed in Services.txt [PATIENT]."""
    enabled = set(load_patient_services())
    unknown = enabled - set(SERVICES)
    if unknown:
        logger.warning("Services.txt [PATIENT] lists unknown service(s): %s", ", ".join(unknown))
    return {n: op for n, op in OPERATIONS.items() if op.service in enabled}


def catalog(operations: Optional[Dict[str, Operation]] = None) -> str:
    """Human-readable operation list for the router prompt."""
    ops = operations if operations is not None else active_operations()
    if not ops:
        return "(no tools are currently available)"
    lines = []
    for op in ops.values():
        params = f" params: {', '.join(op.params)}" if op.params else ""
        mark = " [needs confirmation — this changes a booking]" if op.writes else ""
        lines.append(f"- {op.name}: {op.description}{params}{mark}")
    return "\n".join(lines)


def call(
    operation: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    patient_id: Optional[int] = None,
    patient_mrn: Optional[str] = None,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """Invoke a whitelisted operation.

    ``patient_id`` comes from the authenticated session and always wins over anything in
    ``payload``. Write operations require ``confirmed=True``.
    """
    ops = active_operations()
    op = ops.get(operation)
    if op is None:
        raise ToolError(
            f"'{operation}' is not something I can do." if operation not in OPERATIONS
            else "That service isn't available right now."
        )

    body: Dict[str, Any] = {k: v for k, v in (payload or {}).items()
                            if k in op.params and v is not None}

    if op.needs_patient:
        if patient_id is None:
            raise ToolError("I need you to be signed in before I can look that up.")
        # Deliberately last, and unconditional: overwrite any model-supplied patient id.
        body["patient_id"] = int(patient_id)

    if op.writes and not confirmed:
        raise ToolError("That change needs to be confirmed first.")

    # Asklepios PostgreSQL: read record / appointments directly by MRN / patients.id.
    if (settings.db_type or "").lower() == "postgresql":
        if operation == "my_record":
            from app.infrastructure.asklepios_patient import fetch_my_record
            try:
                return fetch_my_record(
                    patient_id=patient_id,
                    patient_mrn=patient_mrn,
                    sections=(payload or {}).get("sections"),
                    lab_limit=int((payload or {}).get("lab_limit") or 12),
                )
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
        if operation == "appointments_list" and patient_id is not None:
            from app.infrastructure.asklepios_patient import fetch_appointments_list
            return fetch_appointments_list(
                patient_id=int(patient_id),
                include_past=bool((payload or {}).get("include_past")),
            )

    logger.info("tool call %s -> %s (patient_id=%s mrn=%s)", operation, op.url,
                body.get("patient_id") if op.needs_patient else patient_id, patient_mrn)
    try:
        resp = requests.post(op.url, json=body, timeout=settings.tool_timeout_seconds)
    except requests.Timeout:
        raise ToolError("The service took too long to respond. Please try again in a moment.")
    except requests.RequestException as exc:
        logger.warning("tool %s unreachable: %s", operation, exc)
        raise ToolError("I can't reach that service at the moment. Please try again shortly.")

    if resp.status_code >= 400:
        detail = ""
        try:
            detail = (resp.json() or {}).get("detail", "")
        except Exception:
            detail = resp.text[:200]
        logger.info("tool %s returned HTTP %s: %s", operation, resp.status_code, detail)
        # 4xx details from these services are written for a patient audience already.
        if 400 <= resp.status_code < 500 and detail:
            raise ToolError(str(detail))
        raise ToolError("Something went wrong on our side. Please try again shortly.")

    try:
        return resp.json()
    except ValueError:
        raise ToolError("I got an unexpected response from that service.")


def health() -> Dict[str, Any]:
    """Probe each active patient service (used by /health and startup logging)."""
    out: Dict[str, Any] = {}
    for name in load_patient_services():
        spec = SERVICES.get(name)
        if spec is None:
            out[name] = {"reachable": False, "error": "unknown service"}
            continue
        try:
            resp = requests.get(f"{spec.base_url}/health", timeout=3)
            out[name] = {"reachable": True, "healthy": resp.status_code == 200,
                         "status": resp.status_code, "url": spec.base_url}
        except requests.RequestException:
            out[name] = {"reachable": False, "healthy": False, "url": spec.base_url}
    return out
