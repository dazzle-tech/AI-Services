"""
Sample Clinical Data for Guideline Assistance Testing
This file contains test data for prototyping the medical guideline assistance feature.
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta

# Sample Patient Records (De-identified)
SAMPLE_PATIENTS = {
    "P001": {
        "patient_id": "P001",
        "age": 67,
        "gender": "M",
        "weight_kg": 82,
        "height_cm": 175,
        "allergies": ["Penicillin", "Sulfa drugs"],
        "comorbidities": [
            "Type 2 Diabetes Mellitus",
            "Hypertension",
            "Chronic Kidney Disease Stage 3"
        ],
        "current_diagnosis": "Acute Coronary Syndrome",
        "admission_date": (datetime.now() - timedelta(days=2)).isoformat(),
        "department": "Cardiology",
        "vitals": {
            "bp_systolic": 145,
            "bp_diastolic": 92,
            "heart_rate": 88,
            "respiratory_rate": 18,
            "temperature_c": 37.2,
            "spo2": 96
        },
        "recent_labs": {
            "creatinine_mg_dl": 1.8,
            "egfr_ml_min": 42,
            "troponin_ng_ml": 2.4,
            "glucose_mg_dl": 165,
            "potassium_meq_l": 4.8
        }
    },
    "P002": {
        "patient_id": "P002",
        "age": 45,
        "gender": "F",
        "weight_kg": 68,
        "height_cm": 162,
        "allergies": ["None known"],
        "comorbidities": ["Asthma", "GERD"],
        "current_diagnosis": "Community-Acquired Pneumonia",
        "admission_date": (datetime.now() - timedelta(days=1)).isoformat(),
        "department": "Pulmonary",
        "vitals": {
            "bp_systolic": 118,
            "bp_diastolic": 76,
            "heart_rate": 102,
            "respiratory_rate": 24,
            "temperature_c": 38.9,
            "spo2": 91
        },
        "recent_labs": {
            "wbc_k_ul": 15.2,
            "crp_mg_l": 145,
            "procalcitonin_ng_ml": 1.8,
            "lactate_mmol_l": 2.1
        }
    },
    "P003": {
        "patient_id": "P003",
        "age": 72,
        "gender": "M",
        "weight_kg": 91,
        "height_cm": 178,
        "allergies": ["Aspirin"],
        "comorbidities": [
            "Atrial Fibrillation",
            "Heart Failure (HFrEF)",
            "Chronic Kidney Disease Stage 4"
        ],
        "current_diagnosis": "Septic Shock",
        "admission_date": datetime.now().isoformat(),
        "department": "ICU",
        "vitals": {
            "bp_systolic": 82,
            "bp_diastolic": 48,
            "heart_rate": 128,
            "respiratory_rate": 32,
            "temperature_c": 39.4,
            "spo2": 88
        },
        "recent_labs": {
            "lactate_mmol_l": 4.8,
            "creatinine_mg_dl": 3.2,
            "wbc_k_ul": 18.5,
            "procalcitonin_ng_ml": 12.4
        }
    }
}

# Sample Active Orders
SAMPLE_ORDERS = {
    "P001": {
        "medications": [
            {
                "order_id": "MED001",
                "medication": "Atorvastatin",
                "dose": "80 mg",
                "route": "PO",
                "frequency": "Daily",
                "indication": "High-intensity statin for ACS",
                "ordered_time": (datetime.now() - timedelta(hours=24)).isoformat()
            },
            {
                "order_id": "MED002",
                "medication": "Metoprolol",
                "dose": "25 mg",
                "route": "PO",
                "frequency": "BID",
                "indication": "Beta-blocker for ACS",
                "ordered_time": (datetime.now() - timedelta(hours=24)).isoformat()
            },
            {
                "order_id": "MED003",
                "medication": "Heparin",
                "dose": "5000 units",
                "route": "IV",
                "frequency": "Continuous infusion",
                "indication": "Anticoagulation for ACS",
                "ordered_time": (datetime.now() - timedelta(hours=20)).isoformat()
            }
        ],
        "procedures": [
            {
                "order_id": "PROC001",
                "procedure": "Coronary angiography",
                "urgency": "Within 24 hours",
                "indication": "Risk stratification for ACS"
            }
        ],
        "labs": [
            {
                "order_id": "LAB001",
                "test": "Serial Troponin",
                "frequency": "Every 6 hours x 3",
                "indication": "ACS monitoring"
            }
        ],
        "imaging": []
    },
    "P002": {
        "medications": [
            {
                "order_id": "MED004",
                "medication": "Ceftriaxone",
                "dose": "1 g",
                "route": "IV",
                "frequency": "Daily",
                "indication": "Community-acquired pneumonia",
                "ordered_time": (datetime.now() - timedelta(hours=12)).isoformat()
            },
            {
                "order_id": "MED005",
                "medication": "Azithromycin",
                "dose": "500 mg",
                "route": "PO",
                "frequency": "Daily",
                "indication": "Atypical coverage for CAP",
                "ordered_time": (datetime.now() - timedelta(hours=12)).isoformat()
            }
        ],
        "procedures": [],
        "labs": [
            {
                "order_id": "LAB002",
                "test": "Blood cultures",
                "frequency": "One time",
                "indication": "Before antibiotic therapy"
            }
        ],
        "imaging": [
            {
                "order_id": "IMG001",
                "imaging": "Chest X-ray PA and Lateral",
                "urgency": "Routine",
                "indication": "Pneumonia evaluation"
            }
        ]
    },
    "P003": {
        "medications": [
            {
                "order_id": "MED006",
                "medication": "Norepinephrine",
                "dose": "0.1 mcg/kg/min",
                "route": "IV",
                "frequency": "Continuous infusion",
                "indication": "Septic shock - vasopressor support",
                "ordered_time": (datetime.now() - timedelta(hours=2)).isoformat()
            },
            {
                "order_id": "MED007",
                "medication": "Normal Saline",
                "dose": "30 mL/kg",
                "route": "IV",
                "frequency": "Bolus over 3 hours",
                "indication": "Septic shock resuscitation",
                "ordered_time": (datetime.now() - timedelta(hours=1)).isoformat()
            }
        ],
        "procedures": [
            {
                "order_id": "PROC002",
                "procedure": "Central venous catheter placement",
                "urgency": "Immediate",
                "indication": "Vasopressor administration and CVP monitoring"
            }
        ],
        "labs": [
            {
                "order_id": "LAB003",
                "test": "Blood cultures x2 (different sites)",
                "frequency": "STAT",
                "indication": "Sepsis workup"
            },
            {
                "order_id": "LAB004",
                "test": "Lactate",
                "frequency": "Every 2 hours",
                "indication": "Sepsis monitoring"
            }
        ],
        "imaging": [
            {
                "order_id": "IMG002",
                "imaging": "CT Abdomen/Pelvis with contrast",
                "urgency": "STAT",
                "indication": "Source control evaluation"
            }
        ]
    }
}

# Clinical Context / Indication
SAMPLE_CLINICAL_CONTEXT = {
    "P001": {
        "presentation": "67-year-old male presenting with chest pain radiating to left arm, associated with diaphoresis. Pain started 2 hours ago.",
        "history": "Known hypertension and diabetes. Previous MI 5 years ago with stent placement to LAD.",
        "physical_exam": "Alert, diaphoretic. Cardiac exam: regular rhythm, no murmurs. Lungs clear.",
        "ecg_findings": "ST-segment elevation in leads V2-V4",
        "working_diagnosis": "STEMI (ST-Elevation Myocardial Infarction)",
        "care_plan": "Reperfusion therapy planned, cardiology consult obtained"
    },
    "P002": {
        "presentation": "45-year-old female with 5 days of productive cough, fever, and dyspnea.",
        "history": "Known asthma, usually well-controlled. No recent travel or sick contacts.",
        "physical_exam": "Febrile, tachypneic. Decreased breath sounds right lower lobe with crackles.",
        "imaging_findings": "Right lower lobe consolidation on chest X-ray",
        "working_diagnosis": "Community-Acquired Pneumonia (CAP) - moderate severity (PSI Class III)",
        "care_plan": "Empiric antibiotic therapy, supportive care, monitor O2 saturation"
    },
    "P003": {
        "presentation": "72-year-old male from nursing home with altered mental status, fever, and hypotension.",
        "history": "Multiple comorbidities. Recent UTI treated 2 weeks ago. Foley catheter in place.",
        "physical_exam": "Lethargic, mottled skin, delayed capillary refill. Tachycardic, tachypneic.",
        "labs_critical": "Lactate 4.8, WBC 18.5, Procalcitonin 12.4, Creatinine elevated from baseline",
        "working_diagnosis": "Septic Shock (suspected urinary source) with acute kidney injury",
        "care_plan": "Sepsis bundle initiated, broad-spectrum antibiotics, fluid resuscitation, vasopressor support"
    }
}

def get_patient_data(patient_id: str) -> Dict[str, Any]:
    """Get complete patient data including orders and context."""
    if patient_id not in SAMPLE_PATIENTS:
        return None
    
    return {
        "patient": SAMPLE_PATIENTS[patient_id],
        "active_orders": SAMPLE_ORDERS.get(patient_id, {}),
        "clinical_context": SAMPLE_CLINICAL_CONTEXT.get(patient_id, {})
    }

def list_all_patients() -> List[str]:
    """Get list of all available patient IDs."""
    return list(SAMPLE_PATIENTS.keys())