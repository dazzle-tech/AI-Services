# Patient Details Availability Analysis

## Fields Shown in Frontend Modal

Based on the patient details modal, the following fields are displayed:

### Patient Information
- ✅ Patient ID (`pat004`)
- ✅ Name (`Emily Johnson`)
- ✅ Date of Birth (`2002-02-14`)
- ✅ Gender (`female`)

### Contact & Insurance
- ✅ Phone (`555-0104`)
- ✅ Email (`emily.johnson@email.com`)
- ⚠️ Insurance Provider (`—` - shown but no data)
- ⚠️ Emergency Contact (`Laura Johnson` - shown but may not be in sample data)

### Medical Profile
- ⚠️ Blood Type (`AB+` - shown but may not be in sample data)
- ❌ Allergies (`—` - not currently queried)
- ❌ Chronic Conditions (`—` - not currently queried)
- ❌ Medications (`—` - not currently queried)
- ❌ Height (cm) (`—` - not currently queried)
- ❌ Weight (kg) (`—` - not currently queried)
- ❌ BMI (`—` - not currently queried)
- ❌ Smoking Status (`—` - not currently queried)
- ❌ Alcohol Use (`—` - not currently queried)
- ❌ Last Checkup Date (`—` - not currently queried)
- ❌ Clinical Notes (`—` - not currently queried)

### Latest Admission
- ✅ Admission Date (`2025-01-11`)
- ✅ Discharge Date (`—`)
- ✅ Diagnosis (`Fever, unspecified`)

## What's Available in Schema (access_control.json)

### ✅ Available in `ap_patient` table:
- `key`, `patient_mrn`, `first_name`, `last_name`, `full_name`, `dob`, `gender_lkey`
- `phone_number`, `mobile_number`, `email`
- `emergency_contact_name`, `emergency_contact_phone`, `emergency_contact_relation_lkey`
- `blood_group_lkey`

### ✅ Available in `ap_encounter` table:
- `actual_start_date` (admission date)
- `discharge_at` (discharge date)
- `encounter_status_lkey`, `encounter_type_lkey`

### ✅ Available in `ap_patient_diagnose` table:
- `diagnose_code`, `description` (diagnosis)

### ✅ Available in other tables (NOT currently queried):
- **Allergies**: `ap_patient_allergies` table
- **Medications**: `ap_prescription_medications` or `ap_drug_order_medications` tables
- **Height/Weight/BMI**: `ap_patient_observation_summary` table (`latestheight`, `latestweight`, `latestbmi`)
- **Chronic Conditions**: `ap_patient_problem` table
- **Insurance**: `ap_patient_insurance` table (`insurance_provider_lkey`)
- **Alcohol Use**: Found in some table (`alcohol_consumption`)
- **Smoking Status**: Need to verify location
- **Clinical Notes**: Need to verify location

## What's Currently Being Queried

The `patient_details.py` service currently only queries:
1. **ap_patient** - All columns
2. **ap_encounter** - Limited columns (key, actual_start_date, discharge_at, encounter_status_lkey, encounter_type_lkey)
3. **ap_patient_diagnose** - Limited columns (key, diagnose_code, description)

## What's Missing from Current Query

The following tables/fields are available in the schema but NOT being queried:
1. ❌ `ap_patient_allergies` - For allergies
2. ❌ `ap_patient_observation_summary` - For height, weight, BMI
3. ❌ `ap_patient_problem` - For chronic conditions
4. ❌ `ap_patient_insurance` - For insurance provider
5. ❌ `ap_prescription_medications` or `ap_drug_order_medications` - For medications
6. ❌ Smoking/Alcohol status tables
7. ❌ Clinical notes tables

## Sample Data Status

The `init_mock_db.py` script only inserts:
- ✅ Basic patient data (4 patients with name, DOB, gender, MRN)
- ✅ Basic encounter data (5 encounters)
- ❌ NO sample data for allergies, medications, observations, insurance, etc.

## Recommendations

1. **Update `patient_details.py`** to join additional tables:
   - `ap_patient_allergies` for allergies
   - `ap_patient_observation_summary` for height/weight/BMI
   - `ap_patient_problem` for chronic conditions
   - `ap_patient_insurance` for insurance provider
   - Medication tables for medications

2. **Update `init_mock_db.py`** to insert sample data for:
   - Allergies
   - Observations (height, weight, BMI)
   - Insurance information
   - Medications
   - Chronic conditions

3. **Frontend**: The modal is already designed to show these fields, but they'll show `—` until the backend queries and populates them.
