# Synopsis

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
3. Watch the charts in the strip under the title. The strip stays fixed at the top of the window while you scroll, so the charts are always in view. The charts update as the circle walks. There is one chart per vital sign. A cursor follows the walking circle across the dates, and a chart draws its line (or point) as the cursor passes each reading. The readout beside the name shows the latest reading so far. A vital sign with no recorded reading says "Not documented". Press a chart with a reading to zoom into its date.
4. Switch the role (Physician, Nurse, Radiologist, Cardiologist) and the objective. Circles resize and the "why it matters" lines change. The summary stays the same.
5. Choose a period (2020, 2022, 2024, This admission) or set a date in "Start from". The line and the charts start at that date and the walk restarts from there; earlier events stay to the left, greyed.
6. Use "Highlight by type" to dim events without removing them.
7. Press the moon button (top right) for dark mode, and the sun to come back. The choice is remembered in the browser, and the first visit follows the system setting.
8. Look at the Patient overview below the story. It is an AR-style panel: a translucent anatomical 3D body (muscle layer with a blue rim, and a glowing spine on the back) with a pulsing marker on the chest (drag it left or right to turn it, use the arrow buttons or Front and Back to see the other side, point at any area to see what the record holds there, and press an area to pin its card), a leader line to the "Chest pain" card, accordions for medical history, allergies, immunizations, current medications, treatment plan, lab results and notes on both sides of the body. Every item shows only what the record holds ("Not documented" otherwise), follows the chosen role and objective, and opens its date in the zoomed story when pressed. The panel follows light and dark mode.
9. Keyboard: Tab to a circle, Left and Right to move between milestones that have appeared, Enter to zoom in, Esc to zoom out.

If the system asks for reduced motion, every milestone appears at once and zooming has no animation; Play story still walks the line on request.

## 3D body credits

The figure is "Human Muscles" by Grab3D (light version, https://grab3d.com/models/anatomy/human-muscles/), released under CC0 1.0 (public domain). `tools/pack_body.py` packs the GLB into `prototype/models/body-muscles.js` (a gzip'd, quantised copy that opens from `file://`; run it again if you swap the model). The page splits the single mesh into body areas by landmark heights (`classify` in `body3d.js`). The figure needs WebGL and `DecompressionStream`; without them the page draws the flat figure instead. Only the chest is linked to the record; every other area reads "Not documented".

## Data and rules

`prototype/data/patient.json` holds a fictional patient built from the acceptance chart. The prototype uses only those facts: a missing fact reads "not documented", one troponin stays one troponin, blood pressure stays `160/100`, and nothing recommends an order or a treatment.

The chart data lives in `measures[].readings` as `{ "date", "values", "text", "synthetic" }`. The record holds one reading, BP `160/100` on 2026-03-12. All other readings (RR, HR, Temp, SpO₂, and the earlier BP values) are made-up sample data so the charts have something to draw. They carry `"synthetic": true`, show hollow points, sit under a "Sample" tag, and the note under the chart row says so. They end on 2026-01-20, before the admission, so nothing contradicts the admission day, and they carry no units. Delete the `synthetic` readings from `patient.json` (and regenerate `patient.js`) to return to record-only charts. If you edit `patient.json`, regenerate `patient.js` so the double-click version matches.
