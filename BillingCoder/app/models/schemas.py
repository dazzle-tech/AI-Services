"""Pydantic models for CodingAssist requests and responses."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# CMS place-of-service codes (subset covering common settings). Source of
# truth in production would be the full CMS POS code list.
VALID_PLACE_OF_SERVICE_CODES = {
    "11", "12", "19", "20", "21", "22", "23", "24", "25", "26",
    "31", "32", "33", "34", "41", "42", "49", "50", "51", "52",
    "53", "54", "55", "56", "57", "58", "60", "61", "62", "65",
    "71", "72", "81", "99",
}


class EncounterMetadata(BaseModel):
    """Administrative facts about a billable encounter.

    These are never inferred from free text -- they come from the system
    of record (EHR/PM) and are validated, not extracted.
    """

    encounter_id: str = Field(..., description="Unique identifier for the encounter.")
    patient_id: str = Field(..., description="Stable patient identifier.")
    date_of_service: str = Field(..., description="YYYY-MM-DD date the service was rendered.")
    place_of_service: str = Field(..., description="CMS place-of-service code, e.g. '11' (office), '22' (outpatient).")
    rendering_provider_npi: str = Field(..., description="10-digit National Provider Identifier.")
    payer_id: Optional[str] = Field(None, description="Identifies which payer's edit/coverage rule set applies.")

    @field_validator("place_of_service")
    @classmethod
    def validate_place_of_service(cls, v: str) -> str:
        """Reject codes outside the CMS place-of-service list."""
        if v not in VALID_PLACE_OF_SERVICE_CODES:
            raise ValueError(f"'{v}' is not a recognized CMS place-of-service code")
        return v

    @field_validator("rendering_provider_npi")
    @classmethod
    def validate_npi(cls, v: str) -> str:
        """Reject NPIs that aren't exactly 10 digits."""
        if not (v.isdigit() and len(v) == 10):
            raise ValueError("rendering_provider_npi must be exactly 10 digits")
        return v


class ClinicalDocument(BaseModel):
    """A single source document contributing to the encounter's documentation."""

    document_type: str = Field(..., description="e.g. 'op_note', 'progress_note', 'radiology_report', 'ed_note'.")
    text: str = Field(..., min_length=1)


class UpstreamEntity(BaseModel):
    """An already-grounded clinical entity from an upstream pipeline (e.g. RadiologyReporter)."""

    text: str
    type: str
    snomed_code: Optional[str] = None
    snomed_display: Optional[str] = None
    radlex_rid: Optional[str] = None
    radlex_display: Optional[str] = None
    umls_cui: Optional[str] = None
    laterality: Optional[str] = None
    measurement: Optional[str] = None
    source: str = "none"


class GenerateChargeRequest(BaseModel):
    """POST body for /api/v1/charges/generate."""

    encounter_metadata: EncounterMetadata
    documents: List[ClinicalDocument] = Field(..., min_length=1)
    upstream_entities: Optional[List[UpstreamEntity]] = None


class CodedEntity(BaseModel):
    """A billable clinical concept extracted from documentation and grounded to a code system."""

    text: str
    kind: str = Field(..., description="'diagnosis' | 'procedure'")
    status: str = Field("confirmed", description="'confirmed' | 'suspected' | 'ruled_out' (diagnosis only)")
    laterality: Optional[str] = None
    units: Optional[int] = None
    code_system: Optional[str] = Field(None, description="'ICD-10-CM' | 'CPT' | 'HCPCS'")
    code: Optional[str] = None
    display: Optional[str] = None
    source: str = "none"


class ComplianceFlag(BaseModel):
    """A deterministic match against the coding-edit or medical-necessity rule sets."""

    rule_type: str = Field(..., description="'ptp_edit' | 'mue' | 'medical_necessity' | 'ruled_out_diagnosis'")
    severity: str = Field(..., description="'blocking' | 'warning'")
    message: str
    affected_codes: List[str] = Field(default_factory=list)


class ChargeLine(BaseModel):
    """A single billable line item."""

    code_system: str = Field(..., description="'CPT' | 'HCPCS'")
    code: str
    description: str
    modifiers: List[str] = Field(default_factory=list)
    units: int = 1
    linked_diagnosis_codes: List[str] = Field(default_factory=list)


class ChargeDraft(BaseModel):
    """The structured charge ticket."""

    charge_lines: List[ChargeLine]
    claim_notes: str


class GenerateChargeResponse(BaseModel):
    """Full pipeline response returned to the client."""

    charge_id: str
    encounter_id: str
    patient_id: str
    date_of_service: str
    generated_at_utc: str
    model_used: str
    normalized_notes: str
    coded_entities: List[CodedEntity]
    compliance_flags: List[ComplianceFlag]
    charge_draft: ChargeDraft
    output_file: str


class HealthResponse(BaseModel):
    """Health-check payload."""

    status: str
    service: str
    version: str
    model: Optional[str]
    openai_configured: bool
    rag_initialized: bool
    rag_term_count: int
    ptp_edit_count: int
    mue_rule_count: int


class CodingEditsSummaryResponse(BaseModel):
    """Quick summary of the deterministic edit rules (no AI call)."""

    ptp_edit_count: int
    mue_rule_count: int
    ptp_edits: List[Dict[str, Any]]
    mue_limits: List[Dict[str, Any]]
