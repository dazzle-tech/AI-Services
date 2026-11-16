# Prompt: Perspective — the document and the HTML prototype

Paste everything below the line into the agent.

---

You are a senior product designer and front-end engineer. Build two deliverables for a product called **Perspective**. Work in a new folder `Perspective/`. Do not reuse earlier Perspective files.

## 1. What Perspective is

Perspective is a general service that turns one body of dated facts into a story told for one person.
The person gives a few inputs: **who they are (role)**, **what they want to do (objective)**, **what to focus on**, **the period**, **the tone**, and **the form** (interactive story, slides, or video).
The service first normalizes the source into one list of dated facts. It then writes one short summary and lays the same facts out on a timeline. Pressing a point on the timeline opens that date in more detail, using only the facts that belong to it.

The idea is general: a hospital chart, a bank customer's history, a student's year, a project, a legal case. **The first use case is a hospital information system.** Treat other places as one short paragraph, not as screens.

## 2. Deliverable A — the document (Word, `.docx`)

Length: 2 pages maximum, portrait, US Letter.
Structure, in this order, with a short contents list at the top (never at the end):

1. **Summary** — three sentences: what it is, who it is for, why it matters.
2. **The idea explained** — a plain, general explanation. How inputs become facts, facts become a summary and a timeline, a timeline point becomes a detailed page.
3. **How it adapts** — a small table: role, what leads, what stays in the background. Rows: Physician on a morning round, Nurse at handover, Radiologist, Cardiologist, Pharmacist, Manager.
4. **Use case: a hospital system** — the morning round example. The doctor opens a patient and sees the reason for admission, the latest measures, allergies, active medicines, and what is not documented. Pressing a milestone opens that date.
5. **Other places** — one short paragraph (bank, school, project, legal case).
6. **Rules that keep it trustworthy** — a short list: every sentence links to a source; a missing fact is called "not documented"; a single result stays a single result; the screen ranks and explains and never hides a recorded event; no orders and no treatment choices.
7. **First step** — one ward, one role, reviewers mark anything wrong.

Style: blue and white, one accent for alerts. Short sentences. Affirmative wording. No filler. Use real Word headings and a real contents list. Check the page count with Word before finishing and keep it at 2.

## 3. Deliverable B — the HTML prototype

One folder, no build step: `index.html`, `styles.css`, `app.js`, plus `data/patient.json`. It must open by double-click and also work from a static server.

### Design direction
Take inspiration from current medical and timeline dashboards on **Dribbble** (search "medical dashboard", "patient timeline", "clinical dashboard", blue and white). Do not copy any shot. Aim for something **professional, modern, and smart**:

- Theme: blue and white. Primary blue `#1d4ed8`, deep blue `#1e3a8a`, soft blue `#eff6ff`, borders `#e2e8f0`, ink `#0f172a`, alert `#be123c`.
- Font: Poppins or Inter. Rounded cards, 16–20 px radius, soft shadows, generous spacing.
- Desktop first at 1440×900, responsive down to a tablet.
- Light, calm, clinical. No clutter.

### Layout (top to bottom)
1. **Header** — Perspective mark, patient banner (name, age, sex, ID, ward), and a **role switcher** (Physician, Nurse, Radiologist, Cardiologist) plus an **objective** selector (Morning round, Handover, Imaging request, Cardiac review).
2. **Summary panel** — the written summary. It is one block of text, the same for every role (it comes from the facts, not from the role). Beside it, a compact strip of latest measures (RR, HR, BP, Temp, SpO₂) with small sparklines, and three side cards: **Needs a look**, **Allergy**, **Not documented**.
3. **Story timeline** — the centrepiece.
4. **Detail drawer** — opens for the pressed point.

### The timeline (horizontal story)
Take the vertical card timeline in the reference photo (a centre line with dots, white cards that alternate sides, each card with a title, a one-line subtitle, and a date block) and turn it **horizontal**:

- One horizontal line across the page. Circles ("milestones") sit on it.
- Cards alternate **above and below** the line, each joined to its circle by a short stem. Each card has a title, a one-line subtitle, optional small icons, and a date block (month, big day, year).
- **It starts from the requested date** (the period start the user chose) and runs forward. A start marker shows the requested date. The line scrolls horizontally with drag, wheel, arrow keys, and Prev/Next buttons.
- **Animation for every milestone and period**: when the line first draws, it extends left to right; each circle pops in, then its card rises and fades in in sequence. Moving to a new period slides the line and re-plays the sequence. A "Play story" button advances milestone by milestone with a moving playhead and a pause control. Respect `prefers-reduced-motion`.
- Period chips above the line (for example 2020 · 2022 · 2024 · This admission). Choosing one animates the line to that period.
- **Pressing a circle** opens the detail drawer for that date: a title, the date, what the record says, the source (author, date, document), related events from the same day, and, where it exists, more detail (values, notes). When a date has no further detail, the drawer says "No further detail in the record" and still shows the source.
- Hover shows a small preview. Focus order and Enter/Space work on every circle. Each circle has an accessible name.

### Highlighting by role and objective
Highlighting **ranks and explains**. It never deletes or hides an event.

- Every event has `type`, `date`, `title`, `description`, `importance`, `source`.
- Each role and objective has a profile that sets, for each event type, a salience: **lead**, **context**, or **quiet**.
- **Lead** events get a stronger circle (larger, filled blue, subtle pulse) and a "Why it matters for you" line on the card. **Context** events are normal. **Quiet** events are smaller and lighter but still pressable.
- Changing the role or the objective re-ranks with an animation (circles resize, cards update their "why it matters" line). The summary text does not change.
- A **Highlight** toggle row lets the user also filter by type (Vitals, Labs, Medicines, Procedures, Notes, Allergies) without removing anything: filtered-out events dim.
- Role profiles:
  - **Physician, morning round**: reason for admission, latest vitals, abnormal results, active medicines, changes since yesterday.
  - **Nurse, handover**: why the patient is here, latest vitals and escalation symptoms, allergies, active high-risk medicines (insulin, anticoagulants, opioids, new starts and stops), abnormal labs. Old procedures stay in history unless tied to a current device, wound, or bleeding precaution.
  - **Radiologist, imaging request**: the clinical question, diagnoses that change what to look for, prior procedures and devices, renal function, documented contrast reaction. Never present a penicillin allergy as a contrast allergy.
  - **Cardiologist, cardiac review**: symptom timeline, cardiac biomarkers exactly as recorded, prior cardiac diagnoses and procedures, blood pressure, cardiac and antithrombotic medicines actually listed.
- Each profile also lists **Not documented** items shown in the side card when absent (for example ECG, a second troponin, renal function, dose, route, frequency).

### Data and clinical rules (mandatory)
Use `data/patient.json` with a fictional patient. Use this acceptance chart:

- 58 years, male. Type 2 diabetes 2022-05-01. Hypertension 2021-03-10.
- Metformin from 2022-05-02, active. Insulin from 2023-11-18, active.
- Troponin 0.8 ng/mL, flagged high, 2026-03-13.
- Blood pressure 160/100 on 2026-03-12.
- Coronary angiography completed 2020-02-15.
- Admission 2026-03-12 for chest pain. Note the same day: admitted with chest pain and shortness of breath.
- Penicillin allergy recorded 2020-01-01.

Rules the prototype must obey:
- Use only these facts. No invented dose, route, frequency, unit, result, trend, or diagnosis.
- A single lab stays a single value. One troponin is not a rise, a fall, or an infarct.
- BP is shown as `160/100` with no unit.
- A missing fact is shown as "not documented", never as "takes none" or "normal".
- Do not describe arteries from the angiogram. State only that it was completed.
- Every card and every sentence in the summary cites its source and date.
- No orders, no contrast protocol, no drug-change advice.
- The summary is identical for all roles.

### Quality bar
- Semantic HTML, keyboard accessible, visible focus rings, WCAG AA contrast.
- No external runtime dependencies except an optional web font. Plain CSS and vanilla JS (or a single small library if it clearly helps).
- Smooth 60 fps animation using transforms and opacity.
- Verify in a browser: take screenshots at 1440×900 and a tablet width, switch through all four roles, press at least three circles, and confirm the angiogram drawer and the "not documented" states. Fix any overlap or clipped text before finishing.

## 4. Finish

- Put the document at `Perspective/Perspective.docx` and the prototype in `Perspective/prototype/`.
- Add a short `Perspective/README.md` with how to open the prototype.
- Report what you built, what you verified in the browser, and anything you could not check.
