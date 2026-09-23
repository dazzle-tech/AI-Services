# Medical Document Processor samples

Synthetic documents for `POST /api/v1/process-document`. They use the same demo
patient as the unit tests: **Jane Doe / P-1001 / female / 1980-05-14**.

Regenerate PDF, DOCX, and PNG from the lab-result text:

```bash
py scripts/generate_samples.py
```

## Patients

| File | Use |
|------|-----|
| `patients/jane_doe.json` | Matching patient for Jane Doe documents |
| `patients/john_smith.json` | Matching patient for the John Smith lab result |
| `patients/existing_documents.json` | Newer lab already on file (supersede check) |

## Documents

| File | Format | Expected path |
|------|--------|----------------|
| `jane_doe_lab_result.txt` | TXT | Valid, no translation → `processed` / `lab_result` |
| `jane_doe_lab_result.csv` | CSV | Same lab result as a table |
| `jane_doe_lab_result.pdf` | PDF | Text-layer PDF of the same report |
| `jane_doe_lab_result.docx` | DOCX | Word copy of the same report |
| `jane_doe_lab_result.png` | PNG | Image OCR path (`OCR_ENGINE=vision`) |
| `jane_doe_radiology_report.txt` | TXT | `processed` / `radiology_report` |
| `jane_doe_prescription.txt` | TXT | `processed` / `prescription` |
| `jane_doe_clinical_note.txt` | TXT | `processed` / `clinical_note` |
| `jane_doe_discharge_summary.txt` | TXT | `processed` / `discharge_summary` |
| `jane_doe_clinical_note_fr.txt` | TXT | With `translate=true` → `processed`, `translated=true` |
| `jane_doe_old_lab_result.txt` | TXT | Dated 2019-03-11 → `irrelevant` |
| `jane_doe_old_lab_result.pdf` | PDF | Same outdated lab as PDF |
| `john_smith_lab_result.txt` | TXT | Upload with Jane Doe → `invalid` (sex/name mismatch) |
| `john_smith_lab_result.pdf` | PDF | Same mismatch case as PDF |

## Quick tests (API on port 8029)

Valid lab result, no translation:

```powershell
curl -X POST http://localhost:8029/api/v1/process-document `
  -F "file=@samples/jane_doe_lab_result.txt" `
  -F "patient=<samples/patients/jane_doe.json" `
  -F "translate=false"
```

PDF / DOCX / CSV / PNG — same patient, swap the file:

```powershell
curl -X POST http://localhost:8029/api/v1/process-document `
  -F "file=@samples/jane_doe_lab_result.pdf" `
  -F "patient=<samples/patients/jane_doe.json" `
  -F "translate=false"
```

French note with translation:

```powershell
curl -X POST http://localhost:8029/api/v1/process-document `
  -F "file=@samples/jane_doe_clinical_note_fr.txt" `
  -F "patient=<samples/patients/jane_doe.json" `
  -F "translate=true" `
  -F "target_language=en"
```

Patient mismatch (John Smith document + Jane Doe record):

```powershell
curl -X POST http://localhost:8029/api/v1/process-document `
  -F "file=@samples/john_smith_lab_result.txt" `
  -F "patient=<samples/patients/jane_doe.json" `
  -F "translate=false"
```

Outdated lab (outside the 180-day window):

```powershell
curl -X POST http://localhost:8029/api/v1/process-document `
  -F "file=@samples/jane_doe_old_lab_result.txt" `
  -F "patient=<samples/patients/jane_doe.json" `
  -F "translate=false"
```

Supersede check (existing newer lab on file):

```powershell
curl -X POST http://localhost:8029/api/v1/process-document `
  -F "file=@samples/jane_doe_lab_result.txt" `
  -F "patient=<samples/patients/jane_doe.json" `
  -F "existing_documents=<samples/patients/existing_documents.json" `
  -F "translate=false"
```

On bash, replace `patient=<samples/patients/jane_doe.json` with
`patient="$(cat samples/patients/jane_doe.json)"`.

Postman file uploads are resolved from `C:\Users\User\Postman`, not from this
folder. The collection uses absolute paths under
`C:/Users/User/Desktop/AI-Services/MedicalDocumentProcessor/samples/`. Re-import
`postman/MedicalDocumentProcessor.postman_collection.json` after pulling path
changes, or pick the file manually in the Body tab.
