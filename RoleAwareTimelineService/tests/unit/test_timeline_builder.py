"""Merge, disagreement, and gap behavior that does not call a model."""
from app.ai.guardrails import acceptable_gap, clean_text, combine_gaps, is_history_procedure
from app.models.schemas import TimelineEvent
from app.services.timeline_builder import assign_ids, merge_events, sort_events
from tests.fixtures.acceptance_chart import ACCEPTANCE_PATIENT


def _event(date, event_type, title, description, source, importance="medium"):
    return TimelineEvent(
        event_id="pending",
        date=date,
        event_type=event_type,
        title=title,
        description=description,
        clinical_importance=importance,
        source=source,
    )


def test_obvious_duplicates_merge_and_disagreements_stay_separate():
    """Same event collapses. Two notes that disagree both remain, with their sources."""
    duplicate = _event(
        "2022-05-02",
        "medication",
        "Metformin",
        "Metformin started on 2022-05-02, status active.",
        "notes",
        "low",
    )
    original = _event(
        "2022-05-02",
        "medication",
        "Metformin",
        "Metformin started on 2022-05-02, status active.",
        "medications",
        "high",
    )
    severe = _event(
        "2026-03-12",
        "symptom",
        "Pain assessment",
        "Pain is severe.",
        "notes",
    )
    mild = _event(
        "2026-03-12",
        "symptom",
        "Pain assessment",
        "Pain is mild.",
        "notes",
    )
    merged = assign_ids(sort_events(merge_events([duplicate, severe, original, mild])))
    metformin = [event for event in merged if event.title == "Metformin"]
    pain = [event for event in merged if event.title == "Pain assessment"]
    assert len(metformin) == 1
    assert metformin[0].clinical_importance == "high"
    assert "medications" in metformin[0].source
    assert "notes" in metformin[0].source
    assert len(pain) == 2
    descriptions = {event.description for event in pain}
    assert descriptions == {"Pain is severe.", "Pain is mild."}


def test_clean_text_keeps_a_single_lab_value_and_drops_a_trend():
    """One troponin value survives. A rise or an infarct does not."""
    corpus = "Troponin 0.8 ng/mL, flagged high, on 2026-03-13."
    cleaned = clean_text(
        "Troponin 0.8 ng/mL, flagged high, on 2026-03-13. The value shows a rise and an infarct.",
        corpus,
    )
    assert "0.8 ng/mL" in cleaned
    assert "rise" not in cleaned.lower()
    assert "infarct" not in cleaned.lower()


def test_old_angiogram_is_history_for_the_nurse_unless_tied_to_a_device():
    """A 2020 angiogram is history. A device mentioned on a procedure is not."""
    admission = _event(
        "2026-03-12",
        "admission",
        "Admission for chest pain",
        "Admission for chest pain.",
        "encounters",
        "high",
    )
    angiogram = _event(
        "2020-02-15",
        "procedure",
        "Coronary angiography",
        "Coronary angiography completed.",
        "procedures",
    )
    device = _event(
        "2020-02-15",
        "procedure",
        "Pacemaker device check",
        "Pacemaker device check recorded.",
        "procedures",
    )
    assert is_history_procedure(angiogram, [angiogram, admission]) is True
    assert is_history_procedure(device, [device, admission]) is False


def test_acceptance_gaps_do_not_treat_missing_facts_as_normal():
    """Each role names the facts this chart does not contain."""
    nurse = " ".join(combine_gaps(["The patient takes none."], ACCEPTANCE_PATIENT, "nurse"))
    radiologist = " ".join(combine_gaps(["Renal function is normal."], ACCEPTANCE_PATIENT, "radiologist"))
    cardiologist = " ".join(combine_gaps([], ACCEPTANCE_PATIENT, "cardiologist"))
    assert "takes none" not in nurse.lower()
    assert "Glucose is not documented." in nurse
    assert "Dose is not documented." in nurse
    assert "is normal" not in radiologist.lower()
    assert "Renal function (creatinine or eGFR) is not documented." in radiologist
    assert "ECG is not documented." in cardiologist
    assert "A second troponin is not documented." in cardiologist
    assert acceptable_gap("Contrast reaction is not documented.") is True
