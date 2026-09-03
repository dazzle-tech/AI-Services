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
        "Allergies penicillin. Non smoker. Non alcoholic. Substance use none. "
        "Last meal light breakfast. Food date 2026-09-02. Last fluid water. Fluid date 2026-09-03. "
        "Previous anesthesia yes. Previous surgery yes. Difficult intubation no. Complication no. "
        "Comments appendectomy in 2018 under general anesthesia, uneventful. "
        "Musculoskeletal chronic right knee pain. Endocrine type 2 diabetes, controlled. "
        "Weight 82 kg. Blood pressure 128 over 82. Pulse 76. Temperature 36.8 C. SpO2 98. "
        "Cardiovascular exam normal S1 S2, no murmurs. Respiratory clear air entry bilaterally. "
        "Skin intact, no lesions. Neck mobility full range. Chest x-ray unremarkable. ECG normal sinus rhythm. "
        "ASA class II, not emergency. Pre-anesthesia orders NPO after midnight, continue home antihypertensives. "
        "Pre-medication midazolam 2 mg IV. Prophylactic antibiotic yes, cefazolin 1 g IV on call to OR."
    ),
    "anesthesia_induction_intraoperative": (
        "Pre-induction assessment date 2026-09-12. Blood pressure 120 over 80. Heart rate 78. "
        "Respiratory rate 16. O2 sat 98. NPO yes. NPO date 2026-09-12. "
        "Pre-medication yes, midazolam 2 mg IV given. Induction method IV induction. "
        "Intubation endotracheal tube. Airway cuffed ETT size 7.5. Position supine. "
        "Anesthesiologist resident Dr. Yara Sabbagh. Anesthesia technician Khaled Nimr."
    ),
    "anesthesia_observation_drugs": (
        "Blood pressure 120 over 80. Heart rate 78. Oxygen supply 2. EtCO2 35. SpO2 98. "
        "Temperature 36.8 C. Tidal volume 450. Respiratory rate 16. FiO2 40. O2 air 2. "
        "Blood loss 20 ml."
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
    "anesthesia_pre_evaluation_plan": "asa",
    "anesthesia_induction_intraoperative": "intraoperativeAnesthesia",
    "anesthesia_observation_drugs": "vitalSign",
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
