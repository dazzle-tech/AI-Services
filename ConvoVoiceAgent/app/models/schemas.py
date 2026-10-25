"""Pydantic schemas for ConvoVoiceAgent."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AnalyzeJsonRequest(BaseModel):
    audio_base64: str
    filename: str = "audio.wav"
    context_type: str = "appointment"
    purpose: str = "soap_note"
    detail_level: str = "standard"
    view_ids: Optional[List[str]] = None


class ViewResult(BaseModel):
    view_id: str
    data: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """SystemDisplayPlugin reshape body — the caller's final payload."""

    results: List[ViewResult]


class DownstreamHealth(BaseModel):
    convoscribe: str
    system_display_plugin: str


class HealthResponse(BaseModel):
    status: str
    downstream: DownstreamHealth
    details: Dict[str, Any] = Field(default_factory=dict)


# --- Ambient draft ---------------------------------------------------------

NoteLanguage = Literal["english", "arabic"]
Specialty = Literal["general_practice", "internal_medicine", "pediatrics", "obgyn"]
NoteLength = Literal["brief", "standard", "detailed"]
NoteForm = Literal["bullets", "prose"]
SectionName = Literal["chief_complaint", "hpi", "review_of_systems", "physical_exam", "assessment_plan"]
SECTION_NAMES: tuple[str, ...] = (
    "chief_complaint",
    "hpi",
    "review_of_systems",
    "physical_exam",
    "assessment_plan",
)


class PatientContext(BaseModel):
    chronic_diseases: List[str] = Field(default_factory=list)
    active_medications: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    last_visit: Optional[Dict[str, Any] | str] = None


class NoteOptions(BaseModel):
    note_language: NoteLanguage = "english"
    instruction_language: Optional[str] = Field(default=None, max_length=32)
    specialty: Specialty = "general_practice"
    note_length: NoteLength = "standard"
    note_form: NoteForm = "prose"
    patient_context: Optional[PatientContext] = None
    # When true, diagnoses carry an ICD-10 code from the local table. When false, diagnoses is empty.
    suggest_icd10: bool = True
    # When true, orders lists suggested orders. When false, orders is empty. The plan text is written either way.
    suggest_orders: bool = True

    @property
    def resolved_instruction_language(self) -> str:
        return (self.instruction_language or "").strip().lower() or self.note_language


class DraftJsonRequest(NoteOptions):
    audio_base64: str
    filename: str = "audio.wav"


class TranscriptItem(BaseModel):
    id: str
    speaker: Literal["doctor", "patient", "other"]
    lang: Literal["en", "ar", "mixed", "unknown"] = "unknown"
    start_ms: int
    end_ms: int
    text: str
    confidence: Optional[float] = None


class Sentence(BaseModel):
    sentence_id: str
    text: str
    segment_ids: List[str] = Field(min_length=1)
    low_confidence: bool = False


class PlanSentence(Sentence):
    """assessment_plan sentence. part routes it to soap_note Assessments or TreatmentPlans."""

    part: Literal["assessment", "plan"]


class Section(BaseModel):
    sentences: List[Sentence] = Field(default_factory=list)


class AssessmentPlanSection(BaseModel):
    sentences: List[PlanSentence] = Field(default_factory=list)


class DraftSections(BaseModel):
    chief_complaint: Section = Field(default_factory=Section)
    hpi: Section = Field(default_factory=Section)
    review_of_systems: Section = Field(default_factory=Section)
    physical_exam: Section = Field(default_factory=Section)
    assessment_plan: AssessmentPlanSection = Field(default_factory=AssessmentPlanSection)


class Diagnosis(BaseModel):
    id: str
    icd10: Optional[str] = None
    label: str
    rank: Literal["primary", "secondary"] = "secondary"
    suspected: bool = False
    chronic: bool = False
    segment_ids: List[str] = Field(min_length=1)


class Order(BaseModel):
    id: str
    kind: Literal["medication", "lab", "imaging", "referral", "follow_up", "sick_leave"]
    payload: Dict[str, Any] = Field(default_factory=dict)
    segment_ids: List[str] = Field(min_length=1)


class Mention(BaseModel):
    kind: Literal["allergy", "warning", "sick_leave"]
    text: str
    segment_ids: List[str] = Field(min_length=1)
    confirm_required: Literal[True] = True


class Instructions(BaseModel):
    language: str
    text: str = ""
    segment_ids: List[str] = Field(default_factory=list)


class Flag(BaseModel):
    kind: Literal["drug_name", "dose"]
    text: str
    segment_ids: List[str] = Field(min_length=1)


class TranscriptionErrorHint(BaseModel):
    """A phrase that may be misheard. The note keeps `heard`; only the physician applies `likely`."""

    heard: str
    likely: str
    segment_ids: List[str] = Field(min_length=1)


class DraftResponse(BaseModel):
    transcript: List[TranscriptItem]
    sections: DraftSections
    soap_note: Dict[str, Any]
    diagnoses: List[Diagnosis] = Field(default_factory=list)
    orders: List[Order] = Field(default_factory=list)
    mentions: List[Mention] = Field(default_factory=list)
    instructions: Instructions
    flags: List[Flag] = Field(default_factory=list)
    possible_transcription_errors: List[TranscriptionErrorHint] = Field(default_factory=list)
    patient_context_used: bool = False
    # Asklepios payloads. record[group] is null when nothing was found for it (do not post it).
    # record_evidence maps "group.field" to transcript segment ids; patient_diagnosis items are "patient_diagnosis.0".
    # record_status is empty|partial|complete per group; missing_required lists required fields still unsaid.
    record: Dict[str, Any] = Field(default_factory=dict)
    record_evidence: Dict[str, List[str]] = Field(default_factory=dict)
    record_status: Dict[str, str] = Field(default_factory=dict)
    missing_required: Dict[str, List[str]] = Field(default_factory=dict)
    elapsed_ms: int


class RegenerateRequest(NoteOptions):
    transcript: List[TranscriptItem] = Field(min_length=1)
    section: SectionName
    instruction: str = Field(default="", max_length=2000)


class RegenerateResponse(BaseModel):
    """The one requested section, in the same shape that section has inside a draft.

    Sentences use the draft sentence fields. soap_note has only the SOAP fields this section fills.
    diagnoses, orders, mentions and instructions are filled only for assessment_plan.
    flags and possible_transcription_errors only cover segments this section cites.
    record has only the keys this section decides.
    """

    section: SectionName
    sentences: List[PlanSentence | Sentence]
    soap_note: Dict[str, Any]
    diagnoses: List[Diagnosis] = Field(default_factory=list)
    orders: List[Order] = Field(default_factory=list)
    mentions: List[Mention] = Field(default_factory=list)
    instructions: Optional[Instructions] = None
    flags: List[Flag] = Field(default_factory=list)
    possible_transcription_errors: List[TranscriptionErrorHint] = Field(default_factory=list)
    patient_context_used: bool = False
    record: Dict[str, Any] = Field(default_factory=dict)
    record_evidence: Dict[str, List[str]] = Field(default_factory=dict)
    elapsed_ms: int
