# Clinical AI In-Chart Integration Plan

**Date:** 22 September 2026  
**Status:** For review and approval  
**Ask:** Approve the in-chart Sign contract, then the new services listed below.

---

## Difference

Our services **draft** (JSON notes, codes, alerts). Epic **files the chart** when the doctor clicks Sign.

| | **Us today** | **Epic / target** |
|---|---|---|
| Where it happens | Separate APIs | Open HIS encounter |
| After “approve” | Flag in our database | Legal note + live orders |
| Lab / pharmacy | Nothing sent | Orders released |
| Doctor’s extra work | Copy into HIS, sign again | Edit cart → one Sign |

**We already have:** ConvoScribe, ORScribe / ORVoiceAgent, BillingCoder, **Chatbot (patient + staff, WhatsApp, OTP/MRN registration)**, summaries, ICU/discharge/nursing, sepsis, labs, guidelines, order validation, radiology imaging.

**We do not have:** an HIS review cart, in-chart Sign, inbox reply drafts, prior-auth / appeals, or local risk prediction. Do not add a second patient chatbot.

Keep shipping OR scribe and radiology imaging. Do not clone Cosmos, MyChart, or Agent Factory.

---

## What we need to do

1. **In-chart contract** — draft → review cart → HIS Sign → audit. AI never auto-commits. HIS is the legal record.
2. **Extend what we have** where it already owns the job (see table).
3. **Add the missing services** below. New folder only if nothing existing can own it.
4. **Done when** a clinician finishes a visit in the HIS: listen → review cart → Sign. Note is filed; orders go to lab/pharmacy.

---

## Services to add

### New services (do not exist today)

| Service | What it does | Epic analog | Phase |
|---|---|---|---|
| **InChartBridge** | Shared draft / cart / Sign / audit with the HIS. All other services call this. | Encounter Sign | 0 |
| **VisitOrderCart** | From visit audio/SOAP: proposed orders, diagnoses, follow-ups for the cart. Does not place orders. | Art order cart | 1 |
| **InboxDraft** | Drafts replies to patient messages with a short chart snapshot. Does not send. | In Basket Art | 1 |
| **PriorAuthDraft** | Builds a prior-authorization packet from the chart (answers + citations). | Penny prior auth | 1 |
| **DenialAppealDraft** | Drafts denial appeal letters with chart evidence and payer-guideline match. | Penny appeals | 1 |
| **ReadmissionLosRisk** | Local 30-day readmission and length-of-stay risk from *our* HIS data. | Curiosity (narrow) | 3 |
| **ImagingFollowUp** | Extracts incidental / follow-up actions from radiology reports for PCP/coordinator. | Art imaging follow-up | 3 |
| **SDOHFlags** | Flags housing, food, transport, financial strain from notes for care management. | Art SDOH | 3 |

### Extend existing (not new folders)

| Existing service | Add |
|---|---|
| **ConvoScribe** | Feed VisitOrderCart; HIS Sign replaces API-only approve |
| **MedicationTestOrdersValidation** + **MedicalGuidelineValidation** | Check cart lines before they are shown |
| **Chatbot** | Already the patient chatbot. Add: pre-visit intake → clinician topic list; plain-language results/AVS (via LabResultInterpreterService); schedule *intent* only (HIS books); InboxDraft as a staff reply mode. Do not send messages automatically. |
| **SummarizationService** | Chart snapshot for Chatbot inbox drafts |
| **LabResultInterpreterService** | Patient-safe wording inside Chatbot |
| **BillingCoder** | Hands charge context to PriorAuthDraft / DenialAppealDraft |
| **ORVoiceAgent** | Pattern to copy for HIS window + Sign |
| **SepsisEarlyDetection** | Pattern to copy for ReadmissionLosRisk |
| **RadiologyReportFilling** | Input to ImagingFollowUp |
| **SpecialistAlertService** | Pattern to copy for SDOHFlags |
| **OCRParsingService** + **AIAutoPopulation** | Later: outside-med recon from scans (Phase 3, if volume exists) |

### Do not add

A second patient chatbot, Cosmos/Curiosity-scale models, Look-Alikes, patient payments portal, Agent Factory, cancer registry, OASIS, transplant packets, marketing microsites, bed-capacity rerouting.

---

## Sequence

| When | Work |
|---|---|
| Weeks 1–2 | Build **InChartBridge**. Wire ConvoScribe to HIS Sign on a test encounter. |
| Weeks 2–6 | Add **VisitOrderCart**, **InboxDraft**, **PriorAuthDraft**, **DenialAppealDraft**. |
| After Sign is live | Extend **Chatbot**: pre-visit intake, plain-language results/AVS, schedule intent. |
| After that | Add **ReadmissionLosRisk**, **ImagingFollowUp**, **SDOHFlags** only if the receiving workflow exists. |

---

## Success

- One Sign in the HIS files the note and releases accepted orders.  
- New services return drafts only; InChartBridge is the only path into the chart.  
- No second approve in the AI app.

---

*Decision support only. No autonomous ordering, messaging, or claims submission.*
