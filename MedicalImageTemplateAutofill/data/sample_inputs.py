"""
Sample clinician inputs / dictations used for quick API testing.
"""

SAMPLE_INPUTS: dict[str, dict[str, str]] = {
    "ct_chest_pe": {
        "title": "CT Chest — suspected PE",
        "input": (
            "55-year-old male with acute shortness of breath and pleuritic chest pain. "
            "D-dimer elevated. CT pulmonary angiogram performed with 75 mL of Omnipaque "
            "350 IV contrast. Filling defects in the right lower lobe segmental pulmonary "
            "arteries consistent with acute pulmonary embolism. No right heart strain. "
            "Small right pleural effusion. No focal consolidation. Heart size normal. "
            "No mediastinal lymphadenopathy. Visualized upper abdomen unremarkable."
        ),
    },
    "us_abdomen_rq_pain": {
        "title": "Ultrasound abdomen — RUQ pain",
        "input": (
            "42-year-old female with right upper quadrant pain, positive Murphy sign, "
            "fever. Liver is normal in size and echotexture, no focal lesions. "
            "Gallbladder is distended with wall thickening (5 mm), pericholecystic fluid, "
            "and multiple mobile gallstones. Sonographic Murphy sign positive. "
            "CBD measures 4 mm, non-dilated. Pancreas unremarkable. Spleen normal. "
            "Kidneys without hydronephrosis. No free fluid."
        ),
    },
    "mri_brain_stroke": {
        "title": "MRI Brain — stroke workup",
        "input": (
            "68-year-old with sudden onset right-sided weakness 3 hours ago. "
            "MRI brain without contrast performed including DWI, ADC, FLAIR, T2, SWI. "
            "Acute infarct in the left middle cerebral artery territory involving the "
            "frontal and parietal cortex with restricted diffusion. No hemorrhage on SWI. "
            "Ventricles normal in size. Posterior fossa unremarkable. Mild chronic small "
            "vessel ischemic changes."
        ),
    },
    "cxr_pneumonia": {
        "title": "Chest X-ray — pneumonia",
        "input": (
            "70-year-old with cough, fever, and productive sputum. PA and lateral chest "
            "radiographs. Right lower lobe consolidation. No pleural effusion or "
            "pneumothorax. Heart size normal. Mediastinum unremarkable. No prior "
            "studies for comparison."
        ),
    },
    "mri_lumbar_radiculopathy": {
        "title": "MRI Lumbar Spine — radiculopathy",
        "input": (
            "45-year-old with chronic low back pain radiating to left leg, L5 distribution. "
            "Sagittal T1, T2, STIR and axial T2 sequences obtained. Alignment maintained. "
            "Mild disc desiccation L4-L5 and L5-S1. Left paracentral disc protrusion at "
            "L4-L5 contacting the left L5 nerve root. Moderate left foraminal narrowing "
            "at L5-S1. Conus terminates at L1, normal signal. No marrow lesion."
        ),
    },
}


def list_samples() -> list[dict]:
    return [
        {"key": key, "title": value["title"], "preview": value["input"][:120] + "..."}
        for key, value in SAMPLE_INPUTS.items()
    ]


def get_sample(key: str) -> dict | None:
    return SAMPLE_INPUTS.get(key)
