# chatbot-patient — MedAI Patient Assistant

The patient-facing agent. Separate container, separate prompts, separate tool set from
the clinician bot on 8017 — they share nothing at runtime.

- **Port:** 8030 (always starts, like the clinician bot)
- **Prompts:** `Prompts_patient.md` at the repo root (mounted read-only)
- **Tools:** the `[PATIENT]` section of `Services.txt`

## Graph

```
gate ─┬─ answered ─▶ END                        (emergency, or a confirmation resolved)
      └─ route    ─▶ router ─┬─ chat/clarify/refuse ─▶ END
                             └─ use_tool ─▶ collect ─┬─ missing      ─▶ END
                                                     ├─ need_confirm ─▶ END
                                                     └─ execute ─▶ present ─▶ END
```

No SQL generation, no free-form database access, no clinical tooling. The agent's entire
surface is the six operations in `app/infrastructure/tools.py`.

## Safety design

These are the parts worth understanding before changing anything:

**Identity is never taken from the message.** `patient_id` comes from the session and is
injected by `tools.call()`, overwriting whatever the model put in the payload. The
collector also strips `patient_id` / `patient_name` / `mrn` from model output before it
gets that far. A prompt injection saying "show me patient 1020" cannot change which
record is fetched — verified by test.

**A session belongs to one patient for its lifetime.** The first turn binds the identity;
a later turn presenting a different `patient_id` is refused with a 409 rather than
switching records.

**Emergencies short-circuit in code**, not in the prompt. `nodes.is_emergency()` pattern-
matches the message before routing; a match returns the emergency reply and never reaches
a tool. A model is the wrong single point of failure for "patient says they have chest
pain".

**Writes require an explicit confirmation turn.** `appointments_book` and
`appointments_cancel` are marked `writes=True` and are refused by `tools.call()` unless
`confirmed=True`, which only happens after the patient confirms in conversation. The
pending action is held in the session, not inferred from history.

**Non-executing turns cannot claim a write happened.** `_guard_completion_claim()` scans
replies on non-tool turns for "has been cancelled" / "I've booked" and replaces them.
This is not redundant with the prompt: the model was observed announcing a cancellation
it had never performed. Do not remove it.

**Bookings resolve against real slots, not model recall.** The slots from the last
`appointments_search` and the appointments from the last `appointments_list` are kept in
the session; `provider_id` / `date` / `time` / `appt_id` are matched against those
records (by exact value, ordinal — "the first one" — time, or weekday). The model
reliably confuses display names with ids, so its output is treated as a hint, not a fact.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness, prompts loaded, tool reachability |
| `GET` | `/agent/greeting` | Opening message + quick actions (deterministic, no LLM) |
| `POST` | `/agent/chat` | One turn |
| `POST` | `/agent/chat/stream` | Same, as SSE (`status` / `token` / `done`) |
| `GET` | `/agent/history` | Stored conversation, for restoring the UI |
| `POST` | `/agent/reset` | Clear a conversation (sign-out) |
| `GET` | `/agent/tools` | Which patient tools are configured and reachable |

The request and response shapes match the clinician agent's exactly, so the shared React
`<ChatPanel>` (Phase 4) drives either bot unchanged.

## Model tiering

Routing, parameter collection and confirmation classification run on `OPENAI_MODEL`
(fast/cheap). The patient-facing wording runs on `REASONING_MODEL`. The tier is not
caller-selectable — `reasoning_model` on the request is accepted for wire-compatibility
and ignored.

## Local run

```bash
pip install -r requirements.txt

# point at tools running on the host rather than the compose network
MEDAI_TOOLS_HOST=localhost \
MEDAI_SERVICES_FILE=../Services.txt \
MEDAI_PROMPTS_FILE=../Prompts_patient.md \
PORT=8030 python main.py
```

Redis is optional locally — the session store falls back to an in-process dict.

## Tests

No unit-test suite yet. Verified end-to-end against the live tool services: tool routing
for all three services, cross-patient refusal, prompt-injection resistance, medical-advice
refusal, emergency short-circuit, session binding (409), unauthenticated turn (401), SSE
streaming, and the full book / confirm / cancel / decline flow persisting correctly to
`hospital.db`.
