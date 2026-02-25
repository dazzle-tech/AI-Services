"""
Sample data for discharge report generation testing
"""

from models.schemas import (
    PatientRecord,
    ClinicalDocumentation,
    ReportTemplate
)


# Sample Patient 1: Post-MI with PCI
SAMPLE_PATIENT_1 = PatientRecord(
    patient_id="DISCH001",
    age=58,
    gender="M",
    admission_date="2025-12-18",
    discharge_date="2025-12-23",
    primary_diagnosis="Acute ST-Elevation Myocardial Infarction (STEMI)",
    secondary_diagnoses=[
        "Hypertension",
        "Hyperlipidemia",
        "Type 2 Diabetes Mellitus"
    ],
    allergies=["Penicillin"],
    medications_on_admission=[
        {"name": "Metformin", "dose": "1000 mg", "frequency": "BID"},
        {"name": "Lisinopril", "dose": "10 mg", "frequency": "Daily"},
        {"name": "Atorvastatin", "dose": "40 mg", "frequency": "Daily"}
    ]
)

SAMPLE_DOCS_1 = ClinicalDocumentation(
    admission_notes="""58-year-old male with history of HTN, HLD, and DM2 presented to ED with sudden onset severe substernal chest pain radiating to left arm, associated with diaphoresis and nausea. Pain started at 6:00 AM while patient was at rest, rated 9/10 in severity. Wife called 911 immediately.

In ED: Initial vitals BP 165/95, HR 102, RR 22, SpO2 95% on RA. Physical exam notable for diaphoresis, but otherwise unremarkable. EKG showed ST-segment elevations in leads II, III, aVF consistent with inferior STEMI. Troponin elevated at 3.2 ng/mL.

Cardiology consulted, patient taken emergently to cardiac catheterization lab.""",
    
    progress_notes=[
        """Hospital Day 1 (12/18): Patient underwent emergent cardiac catheterization. 100% occlusion of RCA noted. Successful PCI with drug-eluting stent placement. Post-procedure patient stable, chest pain resolved. Started on dual antiplatelet therapy (aspirin + ticagrelor), high-intensity statin, beta-blocker, ACE inhibitor. Transferred to CCU for monitoring. TTE ordered for tomorrow morning.""",
        
        """Hospital Day 2 (12/19): Patient doing well overnight. No chest pain. Vitals stable. TTE shows LVEF 45% with inferolateral wall hypokinesis. Discussed cardiac rehab and lifestyle modifications. Patient ambulating in hallway with PT. Labs show improving troponin, stable renal function. Continue current medications.""",
        
        """Hospital Day 3 (12/20): Continued recovery. Patient tolerating medications well. Education provided on heart healthy diet, smoking cessation (patient is former smoker), medication compliance. Cardiology recommends discharge home with close follow-up.""",
        
        """Hospital Day 4 (12/21): Patient ready for discharge. Final labs reviewed - normal. Discharge medications reconciled. Follow-up arranged with cardiology in 1 week. Cardiac rehab referral placed. Patient verbalized understanding of discharge instructions.""",
        
        """Hospital Day 5 (12/22-12/23): Patient remained stable. Discharge today."""
    ],
    
    procedures_performed=[
        {
            "name": "Coronary angiography with PCI",
            "date": "2025-12-18",
            "result": "Successful PCI to RCA with drug-eluting stent placement. Final TIMI 3 flow achieved."
        },
        {
            "name": "Transthoracic Echocardiogram",
            "date": "2025-12-19",
            "result": "LVEF 45%, inferolateral wall hypokinesis, no valvular abnormalities"
        }
    ],
    
    lab_results={
        "admission": {
            "troponin_ng_ml": 3.2,
            "bnp_pg_ml": 245,
            "creatinine_mg_dl": 1.1,
            "glucose_mg_dl": 185,
            "hba1c_percent": 7.8
        },
        "discharge": {
            "troponin_ng_ml": 0.4,
            "creatinine_mg_dl": 1.0,
            "glucose_mg_dl": 142
        }
    },
    
    imaging_results=[
        {
            "study": "Chest X-ray (12/18)",
            "findings": "Clear lung fields, normal cardiac silhouette, no acute cardiopulmonary process"
        },
        {
            "study": "Transthoracic Echo (12/19)",
            "findings": "LVEF 45%, inferolateral hypokinesis, no pericardial effusion, trace MR"
        }
    ],
    
    consultation_notes=[
        "Cardiology: Patient appropriate for PCI. Will perform emergent catheterization.",
        "Cardiology follow-up (Day 3): Patient doing well post-PCI. Recommend outpatient cardiac rehab and close follow-up."
    ]
)

# Standard discharge report template
STANDARD_TEMPLATE = ReportTemplate(
    template_name="Standard Discharge Summary",
    sections=[
        "Chief Complaint",
        "History of Present Illness",
        "Past Medical History",
        "Allergies",
        "Hospital Course",
        "Procedures Performed",
        "Laboratory and Imaging Findings",
        "Discharge Diagnosis",
        "Discharge Medications",
        "Discharge Instructions and Follow-Up"
    ],
    required_fields=[
        "admission_date",
        "discharge_date",
        "primary_diagnosis",
        "discharge_medications"
    ],
    format_type="standard"
)

# Cardiac-specific template
CARDIAC_TEMPLATE = ReportTemplate(
    template_name="Cardiac Discharge Summary",
    sections=[
        "Chief Complaint",
        "History of Present Illness",
        "Cardiac Risk Factors",
        "Hospital Course and Interventions",
        "Cardiac Catheterization Findings",
        "Echocardiographic Findings",
        "Discharge Diagnosis",
        "Discharge Medications with Cardiac Indications",
        "Cardiac Rehabilitation Referral",
        "Follow-Up and Monitoring"
    ],
    required_fields=[
        "admission_date",
        "discharge_date",
        "primary_diagnosis",
        "cardiac_procedure_details",
        "lvef"
    ],
    format_type="detailed"
)


def get_sample_discharge_patient(patient_id: str = "DISCH001"):
    """Get sample patient for discharge report testing."""
    if patient_id == "DISCH001":
        return {
            "patient": SAMPLE_PATIENT_1,
            "documentation": SAMPLE_DOCS_1
        }
    return None


def get_sample_template(template_name: str = "standard"):
    """Get sample report template."""
    if template_name.lower() == "standard":
        return STANDARD_TEMPLATE
    elif template_name.lower() == "cardiac":
        return CARDIAC_TEMPLATE
    return STANDARD_TEMPLATE