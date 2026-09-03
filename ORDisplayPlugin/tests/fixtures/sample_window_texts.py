"""Example dictations for the eight OR windows."""

SAMPLE_TEXTS = {
    "nursing_verification_of_marking_site": (
        "Site side and level documented. Pre-procedural check list completed. "
        "The procedure surgical consent completed, signed by patient. "
        "Site marked on the left knee, lateral aspect."
    ),
    "nursing_time_out": (
        "Time out. Correct patient confirmed by wristband. "
        "Correct procedure right total knee replacement. Correct site and side. "
        "Correct patient position supine. Verification of site markings. "
        "Availability of correct implants, size 4 tray open. "
        "Surgeon Dr. Omar Haddad staff id stf_2041. Nurse Lina Odeh staff id stf_5590."
    ),
    "nursing_intraoperative": (
        "Operation date 2026-09-03. Time in to operation room 08:15. "
        "Time out from operation room 10:40. Room ROOM1. "
        "Scrub nurse 1 Lina Odeh. Scrub nurse 2 Maha Saleh. Circulate nurse 1 Rana Zaid. "
        "Surgeon Dr. Omar Haddad. Surgeon assist 1 Dr. Sami Khalil. Anesthesiologist Dr. Rami Nasser. "
        "Anesthesia type general. Position supine. Left arm tucked, padding at both heels. "
        "Skin prepared with povidone iodine. Incision site right knee, midline anterior. "
        "Foley catheter size 16, urine output 250 cc, color clear yellow. "
        "Tourniquet start 08:30 end 09:45, duration 75 minutes, pressure 300 mmHg, site right thigh. "
        "Diathermia electro surgical unit ESU_02, dispersive electrode left thigh, cutting 30, coagulation 25, "
        "skin before intact no redness, skin after intact. Laser not applicable. "
        "Hemovac drain 2 at suprapatellar pouch. Chest tube size 28 right pleural cavity. "
        "Other drain Blake drain 1 subcutaneous, lateral. "
        "Pathology specimens 2, synovial tissue, medial compartment. Frozen section 1, distal femur margin. "
        "Removed organ description excised meniscal fragment, approx 2 cm."
    ),
    "nursing_sign_out": (
        "Sign out. Name of surgical invasive procedure right total knee replacement. "
        "Completion of instruments sponge and needle counts yes, counts correct x2. "
        "Labeling of specimens yes, two pathology labels read aloud. "
        "Equipment problems no."
    ),
    "anesthesia_pre_evaluation_plan": (
        "ASA II. Airway assessment Mallampati 2. Allergies NKDA. Medications lisinopril. "
        "Comorbidities hypertension. NPO since midnight. Planned anesthesia general. "
        "Planned airway ETT. Risk notes standard. Consent for anesthesia obtained."
    ),
    "anesthesia_induction_intraoperative": (
        "Induction time 08:22. Giving propofol 150 mg. Airway technique used ETT. "
        "Intubation attempts 1. Ventilation mode volume control. Lines placed 18 gauge IV. "
        "Positioning supine. Intraoperative events uneventful."
    ),
    "anesthesia_observation_drugs": (
        "Heart rate 72. Blood pressure 120/80. SpO2 99%. Temperature 36.5 C. "
        "Giving fentanyl 50 mcg route IV. Crystalloid 500 ml. "
        "Estimated blood loss 50 ml. Urine output 100 ml."
    ),
    "operative_note": (
        "Operative note time 08:15. Type of anesthesia general. Main surgeon Dr. Omar Haddad. "
        "Surgeon's assistant Dr. Yousef Amr. Surgical start time 2026-08-17T08:30:00. "
        "Surgical end time 2026-08-17T10:05:00. Operation note: Under general anesthesia the patient was positioned supine. "
        "A midline anterior incision was made over the right knee. The joint was entered through a medial parapatellar approach. "
        "Femoral and tibial cuts were performed using standard instrumentation. Trial components were inserted and satisfactory alignment and stability were confirmed. "
        "Final components were cemented in place. Hemostasis was achieved and the wound closed in layers over a Hemovac drain. "
        "Complication none. Estimated blood loss 20 ml."
    ),
}

EXPECTED_NONEMPTY = {
    "nursing_verification_of_marking_site": "siteMarking",
    "nursing_time_out": "staff",
    "nursing_intraoperative": "operationStaff",
    "nursing_sign_out": "checklist",
    "anesthesia_pre_evaluation_plan": "asa_class",
    "anesthesia_induction_intraoperative": "intubation_attempts",
    "anesthesia_observation_drugs": "estimated_blood_loss_ml",
    "operative_note": "operationNote",
}

WINDOW_PATHS = {
    "nursing_verification_of_marking_site": "/api/v1/windows/nursing/verification-of-marking-site",
    "nursing_time_out": "/api/v1/windows/nursing/time-out",
    "nursing_intraoperative": "/api/v1/windows/nursing/intraoperative",
    "nursing_sign_out": "/api/v1/windows/nursing/sign-out",
    "anesthesia_pre_evaluation_plan": "/api/v1/windows/anesthesia/pre-evaluation-plan",
    "anesthesia_induction_intraoperative": "/api/v1/windows/anesthesia/induction-intraoperative",
    "anesthesia_observation_drugs": "/api/v1/windows/anesthesia/observation-drugs",
    "operative_note": "/api/v1/windows/operative-note",
}

WINDOW_ROLES = {
    "nursing_verification_of_marking_site": "nurse",
    "nursing_time_out": "nurse",
    "nursing_intraoperative": "nurse",
    "nursing_sign_out": "nurse",
    "anesthesia_pre_evaluation_plan": "anesthetist",
    "anesthesia_induction_intraoperative": "anesthetist",
    "anesthesia_observation_drugs": "anesthetist",
    "operative_note": "surgeon",
}

GARBLED_TEXT = "asdf qwer zxcv lorem ipsum dolor sit amet"
