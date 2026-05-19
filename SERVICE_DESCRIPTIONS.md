# Service Descriptions

This document provides a short functional description of the following services in this repository:

- `LabResultInterpreterService`
- `NurseTaskPrioritizationService`
- `PatientTimelineService`
- `SmartDischargePlannerService`
- `SepsisEarlyDetection`

## LabResultInterpreterService

**Purpose:**  
Interprets lab results with optional patient context and historical comparison data. The service highlights abnormal findings, identifies meaningful patterns and trends, and suggests follow-up considerations.

**Typical input:**  
Structured lab values, optional patient demographics and conditions, medications, clinical context, and prior lab history.

**Typical output:**  
A structured interpretation containing severity, key findings, detected patterns, trends, follow-up considerations, and a safety disclaimer.

**Main endpoint:**  
`POST /api/v1/interpret-labs`

**Important note:**  
This service supports interpretation only and does not provide an independent diagnosis.

## NurseTaskPrioritizationService

**Purpose:**  
Ranks nursing tasks by urgency and clinical importance so care teams can focus on the highest-priority actions first.

**Typical input:**  
Patient monitoring data, abnormal findings, medication timing, pending nursing tasks, and operational context for the unit or assigned patients.

**Typical output:**  
A prioritized task list with ranking, rationale, and traceable source signals that explain why each task was elevated.

**Main endpoint:**  
`POST /api/v1/prioritize-tasks`

**Important note:**  
This service supports prioritization and does not replace nursing judgment.

## PatientTimelineService

**Purpose:**  
Builds a chronological timeline of clinically important events from structured and semi-structured patient data.

**Typical input:**  
Diagnoses, medications, lab results, procedures, encounters, allergies, vital signs, and free-text clinical notes.

**Typical output:**  
A validated timeline of significant patient events in chronological order, with preserved medical terminology, numeric values, and traceability to source data.

**Main endpoint:**  
`POST /api/v1/generate-timeline`

**Important note:**  
This service is useful when hospital systems need a clear, traceable summary of a patient's clinical history.

## SmartDischargePlannerService

**Purpose:**  
Assesses discharge readiness and helps organize discharge planning using both clinical and operational patient information.

**Typical input:**  
Patient context, latest clinical status, pending tests, active problems, current and planned medications, follow-up logistics, and patient education status.

**Typical output:**  
A structured discharge planning assessment that includes readiness status, blockers, follow-up considerations, medication reconciliation concerns, and a draft discharge planning summary.

**Main endpoint:**  
`POST /api/v1/plan-discharge`

**Important note:**  
This service supports discharge planning only and does not make the final discharge decision.

## SepsisEarlyDetection

**Purpose:**  
Analyzes patient time-series data to identify early signs of sepsis risk and produce a structured clinical risk assessment.

**Typical input:**  
Patient observations and 24-hour clinical data such as vitals, labs, organ dysfunction indicators, and other sepsis-relevant signals. The service can also run against built-in sample patient data.

**Typical output:**  
A sepsis risk assessment that includes qSOFA, SIRS, SOFA-related reasoning, organ dysfunction mapping, and short-term risk forecasting.

**Main endpoints:**  
`POST /api/v1/analyses`  
`POST /api/v1/patients/{patient_id}/analyses`

**Important note:**  
The service folder is named `SepsisEarlyDetection`, while the API and README also refer to the product as `SepsisSentinel`.
