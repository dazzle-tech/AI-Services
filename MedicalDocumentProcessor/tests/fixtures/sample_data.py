"""Sample data for testing."""
from io import BytesIO

from docx import Document
from PIL import Image

from app.models.schemas import ExistingDocumentSummary, PatientInfo

# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------
SAMPLE_PATIENT = PatientInfo(
    patient_id="P-1001",
    full_name="Jane Doe",
    sex="female",
    date_of_birth="1980-05-14",
)

SAMPLE_PATIENT_MALE = PatientInfo(
    patient_id="P-2002",
    full_name="John Smith",
    sex="male",
    date_of_birth="1975-01-01",
)

# ---------------------------------------------------------------------------
# Sample extracted text per document type
# ---------------------------------------------------------------------------
SAMPLE_LAB_RESULT_TEXT = """LABORATORY REPORT
Patient: Jane Doe
Sex: Female
Date of Birth: 1980-05-14
Test Date: 2026-08-01
Ordering Provider: Dr. Amina Hassan

Test Name        Value   Unit      Reference Range   Flag
WBC               11.2   10^9/L    4.0-11.0           high
Hemoglobin        13.5   g/dL      12.0-16.0          normal
"""

SAMPLE_OLD_LAB_RESULT_TEXT = """LABORATORY REPORT
Patient: Jane Doe
Sex: Female
Date of Birth: 1980-05-14
Test Date: 2019-03-11
Ordering Provider: Dr. Amina Hassan

Test Name        Value   Unit      Reference Range   Flag
WBC               7.2    10^9/L    4.0-11.0           normal
"""

SAMPLE_RADIOLOGY_TEXT = """RADIOLOGY REPORT
Patient: Jane Doe
Sex: Female
Study Date: 2026-07-20
Modality: X-Ray
Body Part: Chest
Findings: No acute cardiopulmonary process.
Impression: Normal chest x-ray.
"""

SAMPLE_PRESCRIPTION_TEXT = """PRESCRIPTION
Patient: Jane Doe
Sex: Female
Date: 2026-08-10
Prescribing Provider: Dr. Amina Hassan

Medication: Amoxicillin 500mg
Frequency: Three times daily
Route: Oral
Duration: 7 days
"""

SAMPLE_CLINICAL_NOTE_TEXT = """CLINICAL NOTE
Patient: Jane Doe
Sex: Female
Date: 2026-08-15
Author: Dr. Amina Hassan

Subjective: Patient reports mild headache for 2 days.
Objective: BP 118/76, HR 72, afebrile.
Assessment: Tension headache.
Plan: OTC analgesics, follow up if worsening.
"""

# Same document, but describing a male patient -- for the patient-mismatch scenario.
SAMPLE_LAB_RESULT_TEXT_MALE = """LABORATORY REPORT
Patient: John Smith
Sex: Male
Date of Birth: 1975-01-01
Test Date: 2026-08-01
Ordering Provider: Dr. Amina Hassan

Test Name        Value   Unit      Reference Range   Flag
WBC               11.2   10^9/L    4.0-11.0           high
"""

SAMPLE_FRENCH_CLINICAL_NOTE_TEXT = """NOTE CLINIQUE
Patient : Jane Doe
Sexe : Feminin
Date : 2026-08-15

Le patient se plaint de maux de tete legers depuis 2 jours.
Tension arterielle 118/76, frequence cardiaque 72.
"""

# ---------------------------------------------------------------------------
# Existing documents (for relevance supersede checks)
# ---------------------------------------------------------------------------
SAMPLE_EXISTING_DOCUMENTS = [
    ExistingDocumentSummary(document_type="lab_result", document_date="2026-08-05"),
]

# ---------------------------------------------------------------------------
# Raw file bytes per supported format
# ---------------------------------------------------------------------------
SAMPLE_TXT_BYTES = SAMPLE_LAB_RESULT_TEXT.encode("utf-8")

SAMPLE_CSV_BYTES = (
    "test_name,value,unit,reference_range,flag\n"
    "WBC,11.2,10^9/L,4.0-11.0,high\n"
    "Hemoglobin,13.5,g/dL,12.0-16.0,normal\n"
).encode("utf-8")

def build_pdf_bytes(text: str) -> bytes:
    """Build a minimal, but genuinely valid (correct xref table), single-page PDF
    with extractable text using only stdlib -- no reportlab dependency needed."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 400 200] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream_content = f"BT /F1 14 Tf 20 150 Td ({text}) Tj ET".encode("latin-1")
    objects.append(b"<< /Length " + str(len(stream_content)).encode() + b" >>\nstream\n"
                    + stream_content + b"\nendstream")

    buffer = bytearray(b"%PDF-1.4\n")
    offsets = [0]  # object 0 is unused (free object)
    for index, body in enumerate(objects, start=1):
        offsets.append(len(buffer))
        buffer += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_offset = len(buffer)
    count = len(objects) + 1
    buffer += f"xref\n0 {count}\n".encode()
    buffer += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        buffer += f"{offset:010d} 00000 n \n".encode()
    buffer += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode()
    return bytes(buffer)


SAMPLE_PDF_BYTES = build_pdf_bytes("Hello Patient Lab Report")

# Corrupted "PDF" -- valid enough extension/content-type to reach the extractor, but
# not parseable content.
SAMPLE_CORRUPTED_PDF_BYTES = b"%PDF-1.4\nthis is not a real pdf body\n%%EOF"


def build_png_bytes() -> bytes:
    """Build a tiny, genuinely valid PNG using Pillow (already a dependency), used
    only to exercise image-format validation in tests that mock the OCR call itself
    (never hits a real vision API in unit tests)."""
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


SAMPLE_PNG_BYTES = build_png_bytes()


def build_docx_bytes(text: str) -> bytes:
    """Build in-memory DOCX bytes from plain text (one paragraph per line)."""
    document = Document()
    for line in text.strip().splitlines():
        document.add_paragraph(line)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


SAMPLE_DOCX_BYTES = build_docx_bytes(SAMPLE_LAB_RESULT_TEXT)
