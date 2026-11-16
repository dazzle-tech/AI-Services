# Perspective

One record. The story changes with the person who is asking. The first use case is a hospital system.

## Contents

- `Perspective.docx` — two-page brief: summary, the idea explained, how it adapts, the hospital use case, other places, rules, first step.
- `prototype/` — the HTML prototype of the hospital screen.

## Open the prototype

Double-click `prototype/index.html`. No build step and no server are needed; `data/patient.js` carries the same data as `data/patient.json` so the page works from disk.

To serve it instead:

```
cd prototype
python -m http.server 8770
```

Then open http://127.0.0.1:8770/index.html.

## What to try

1. Watch the story. A circle starts at the requested date and walks slowly along the line. Each milestone and its card appear, with animation, as the circle reaches it. Play story pauses, resumes, and replays the walk.
2. Press a circle (or a number in the summary). The view zooms into that date and a new story line starts. The circle walks through every event on that date, and each card shows its detail and source. A date with nothing more says "No further detail in the record". Use Earlier date and Later date to move between dates, and Back to story (or Esc) to zoom out. The main walk picks up where it paused.
3. Switch the role (Physician, Nurse, Radiologist, Cardiologist) and the objective. Circles resize and the "why it matters" lines change. The summary stays the same.
4. Choose a period (2020, 2022, 2024, This admission) or set a date in "Start from". The line starts at that date and the walk restarts from there; earlier events stay to the left, greyed.
5. Use "Highlight by type" to dim events without removing them.
6. Keyboard: Tab to a circle, Left and Right to move between milestones that have appeared, Enter to zoom in, Esc to zoom out.

If the system asks for reduced motion, every milestone appears at once and zooming has no animation; Play story still walks the line on request.

## Data and rules

`prototype/data/patient.json` holds a fictional patient built from the acceptance chart. The prototype uses only those facts: a missing fact reads "not documented", one troponin stays one troponin, blood pressure stays `160/100`, and nothing recommends an order or a treatment. If you edit `patient.json`, regenerate `patient.js` so the double-click version matches.
