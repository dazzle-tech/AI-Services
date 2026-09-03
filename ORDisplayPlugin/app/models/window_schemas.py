# TODO: reconcile with real EMR/UI field names

"""Placeholder clinical field schemas for the eight OR window/sub-tab screens.

Every field is Optional — a single dictation will not cover the full window.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _WindowFields(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CountItem(_WindowFields):
    type: Optional[str] = None
    result: Optional[str] = None
    timestamp: Optional[str] = None


class DrugDoseItem(_WindowFields):
    drug: Optional[str] = None
    dose: Optional[str] = None
    time: Optional[str] = None


class VitalItem(_WindowFields):
    time: Optional[str] = None
    hr: Optional[str] = None
    bp: Optional[str] = None
    spo2: Optional[str] = None
    etco2: Optional[str] = None
    temp: Optional[str] = None


class DrugAdminItem(_WindowFields):
    drug: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    time: Optional[str] = None


class FluidItem(_WindowFields):
    fluid: Optional[str] = None
    volume_ml: Optional[str] = None
    time: Optional[str] = None


class BloodProductItem(_WindowFields):
    product: Optional[str] = None
    volume_ml: Optional[str] = None
    time: Optional[str] = None


SiteMarkingStatus = Literal[
    "MARKED",
    "NOT_MARKED_SINGLE_ORGAN",
    "NOT_MARKED_PREMATURE_INFANT_OR_TEETH",
    "NOT_MARKED_PATIENT_REFUSED",
    "NOT_STATED",
]

SITE_MARKING_STATUS_TO_MARKED: dict[str, bool | None] = {
    "MARKED": True,
    "NOT_MARKED_SINGLE_ORGAN": False,
    "NOT_MARKED_PREMATURE_INFANT_OR_TEETH": False,
    "NOT_MARKED_PATIENT_REFUSED": False,
    "NOT_STATED": None,
}

VERIFICATION_CHECKLIST_TEMPLATE: list[dict] = [
    {
        "key": "site_side_level_documented",
        "label": "Site / Side / Level documented, if applicable",
        "checked": None,
        "note": "",
    },
    {
        "key": "pre_procedural_checklist_completed",
        "label": "Pre-Procedural Check List Completed",
        "checked": None,
        "note": "",
    },
    {
        "key": "procedure_surgical_consent_completed",
        "label": "The Procedure/Surgical Consent Completed",
        "checked": None,
        "note": "",
    },
    {
        "key": "anesthesia_consent_completed",
        "label": "The Anesthesia Consent Completed, if applicable",
        "checked": None,
        "note": "",
    },
]


class ChecklistItem(_WindowFields):
    key: str
    label: str
    checked: Optional[bool] = None
    note: str = ""

    @field_validator("note", mode="before")
    @classmethod
    def _note_or_empty(cls, value: object) -> str:
        return "" if value is None else str(value)


class SiteMarking(_WindowFields):
    marked: Optional[bool] = None
    status: Optional[SiteMarkingStatus] = None
    note: str = ""

    @model_validator(mode="after")
    def sync_marked_from_status(self) -> "SiteMarking":
        if self.status is None:
            self.status = "NOT_STATED"
        self.marked = SITE_MARKING_STATUS_TO_MARKED.get(self.status)
        return self


class NursingVerificationOfMarkingSiteFields(_WindowFields):
    checklist: Optional[List[ChecklistItem]] = None
    siteMarking: Optional[SiteMarking] = Field(default=None)


TIME_OUT_CHECKLIST_TEMPLATE: list[dict] = [
    {"key": "correct_patient", "label": "Correct Patient", "checked": None, "note": ""},
    {"key": "correct_procedure", "label": "Correct Procedure", "checked": None, "note": ""},
    {"key": "correct_site_and_side", "label": "Correct Site and Side", "checked": None, "note": ""},
    {"key": "correct_patient_position", "label": "Correct Patient Position", "checked": None, "note": ""},
    {"key": "verification_of_site_markings", "label": "Verification of site markings", "checked": None, "note": ""},
    {
        "key": "availability_of_correct_implants_equipment",
        "label": "Availability of correct implants / special equipment",
        "checked": None,
        "note": "",
    },
]


class StaffMember(_WindowFields):
    staffId: Optional[str] = None
    displayName: Optional[str] = None


class TimeOutStaff(_WindowFields):
    surgeon: StaffMember = Field(default_factory=StaffMember)
    nurse: StaffMember = Field(default_factory=StaffMember)


class NursingTimeOutFields(_WindowFields):
    checklist: Optional[List[ChecklistItem]] = None
    staff: Optional[TimeOutStaff] = None


SIGN_OUT_CHECKLIST_TEMPLATE: list[dict] = [
    {
        "key": "name_of_surgical_invasive_procedure",
        "label": "Name of surgical/invasive procedure",
        "checked": None,
        "response": None,
        "note": "",
    },
    {
        "key": "instruments_sponge_needle_counts_completed",
        "label": "Completion of instruments, sponge and needle counts",
        "checked": None,
        "response": None,
        "note": "",
    },
    {
        "key": "labeling_of_specimens",
        "label": "Labeling of specimens, if present labels are read aloud",
        "checked": None,
        "response": None,
        "note": "",
    },
    {
        "key": "address_any_equipment_problems",
        "label": "Address any equipment problems",
        "checked": None,
        "response": None,
        "note": "",
    },
]


class SignOutChecklistItem(_WindowFields):
    key: str
    label: str
    checked: Optional[bool] = None
    response: Optional[str] = None
    note: str = ""

    @field_validator("note", mode="before")
    @classmethod
    def _note_or_empty(cls, value: object) -> str:
        return "" if value is None else str(value)


class NursingSignOutFields(_WindowFields):
    checklist: Optional[List[SignOutChecklistItem]] = None


class OperationStaff(_WindowFields):
    date: Optional[str] = None
    timeInToOperationRoom: Optional[str] = None
    timeOutFromOperationRoom: Optional[str] = None
    room: Optional[str] = None
    scrubNurse1: Optional[str] = None
    scrubNurse2: Optional[str] = None
    circulateNurse1: Optional[str] = None
    surgeon: Optional[str] = None
    surgeonAssist1: Optional[str] = None
    anesthesiologist: Optional[str] = None


class AnesthesiaTypeBlock(_WindowFields):
    type: Optional[str] = None


class PositionBlock(_WindowFields):
    position: Optional[str] = None
    note: str = ""

    @field_validator("note", mode="before")
    @classmethod
    def _note_or_empty(cls, value: object) -> str:
        return "" if value is None else str(value)


class SkinPreparationAndIncision(_WindowFields):
    preparationSkinWith: Optional[str] = None
    incisionSite: Optional[str] = None


class FoleyCatheter(_WindowFields):
    na: Optional[bool] = None
    catheterSize: Optional[int] = None
    urineOutputCc: Optional[int] = None
    color: Optional[str] = None


class Tourniquet(_WindowFields):
    na: Optional[bool] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    totalDurationMinutes: Optional[int] = None
    pressureMmHg: Optional[int] = None
    site: Optional[str] = None


class DiathermiaAndLaser(_WindowFields):
    na: Optional[bool] = None
    electroSurgicalUnit: Optional[str] = None
    dispersiveElectrodeSite: Optional[str] = None
    electroRangeCutting: Optional[str] = None
    electroRangeCoagulation: Optional[str] = None
    skinConditionBefore: Optional[str] = None
    skinConditionAfter: Optional[str] = None
    note: str = ""

    @field_validator("note", mode="before")
    @classmethod
    def _note_or_empty(cls, value: object) -> str:
        return "" if value is None else str(value)

    @field_validator("electroRangeCutting", "electroRangeCoagulation", mode="before")
    @classmethod
    def _electro_range_as_str(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        return str(value)


class LaserBlock(_WindowFields):
    na: Optional[bool] = None
    pulseEnergy: Optional[str] = None
    frequency: Optional[str] = None
    stoneEffect: Optional[str] = None
    laserFiber: Optional[str] = None
    note: str = ""

    @field_validator("note", mode="before")
    @classmethod
    def _note_or_empty(cls, value: object) -> str:
        return "" if value is None else str(value)


class DrainEntry(_WindowFields):
    type: Optional[str] = None
    numberOfDrains: Optional[int] = None
    location: Optional[str] = None
    size: Optional[int] = None
    otherLabel: Optional[str] = None


class DrainsBlock(_WindowFields):
    na: Optional[bool] = None
    entries: Optional[List[DrainEntry]] = None


class SpecimenEntry(_WindowFields):
    type: Optional[str] = None
    numberOfSamples: Optional[int] = None
    location: Optional[str] = None
    otherLabel: Optional[str] = None
    description: Optional[str] = None


class SpecimensBlock(_WindowFields):
    na: Optional[bool] = None
    entries: Optional[List[SpecimenEntry]] = None


class NursingIntraoperativeFields(_WindowFields):
    operationStaff: Optional[OperationStaff] = None
    anesthesia: Optional[AnesthesiaTypeBlock] = None
    position: Optional[PositionBlock] = None
    skinPreparationAndIncision: Optional[SkinPreparationAndIncision] = None
    foleyCatheter: Optional[FoleyCatheter] = None
    tourniquet: Optional[Tourniquet] = None
    diathermiaAndLaser: Optional[DiathermiaAndLaser] = None
    laser: Optional[LaserBlock] = None
    drains: Optional[DrainsBlock] = None
    specimens: Optional[SpecimensBlock] = None


class AnesthesiaPreEvaluationPlanFields(_WindowFields):
    asa_class: Optional[str] = None
    airway_assessment: Optional[str] = None
    known_allergies: Optional[List[str]] = None
    current_medications: Optional[List[str]] = None
    comorbidities: Optional[List[str]] = None
    npo_status: Optional[str] = None
    planned_anesthesia_type: Optional[str] = None
    planned_airway_technique: Optional[str] = None
    risk_notes: Optional[str] = None
    consent_for_anesthesia: Optional[bool] = None


class AnesthesiaInductionIntraoperativeFields(_WindowFields):
    induction_time: Optional[str] = None
    induction_agents: Optional[List[DrugDoseItem]] = None
    airway_technique_used: Optional[str] = None
    intubation_attempts: Optional[int] = None
    ventilation_mode: Optional[str] = None
    lines_placed: Optional[List[str]] = None
    positioning: Optional[str] = None
    intraoperative_events: Optional[str] = None
    notes: Optional[str] = None


class AnesthesiaObservationDrugsFields(_WindowFields):
    vitals: Optional[List[VitalItem]] = None
    drugs_administered: Optional[List[DrugAdminItem]] = None
    fluids_administered: Optional[List[FluidItem]] = None
    blood_products_administered: Optional[List[BloodProductItem]] = None
    estimated_blood_loss_ml: Optional[str] = None
    urine_output_ml: Optional[str] = None
    notes: Optional[str] = None


class OperativeDetails(_WindowFields):
    time: Optional[str] = None
    typeOfAnesthesia: Optional[str] = None


class OperativeNoteOperationStaff(_WindowFields):
    mainSurgeon: Optional[str] = None
    surgeonsAssistant: Optional[str] = None
    surgicalStartTime: Optional[str] = None
    surgicalEndTime: Optional[str] = None


class OperativeNoteFields(_WindowFields):
    operativeDetails: Optional[OperativeDetails] = None
    operationStaff: Optional[OperativeNoteOperationStaff] = None
    operationNote: Optional[str] = None
    complication: Optional[str] = None
    estimatedBloodLossMl: Optional[int] = None


WINDOW_SCHEMAS = {
    "nursing_verification_of_marking_site": NursingVerificationOfMarkingSiteFields,
    "nursing_time_out": NursingTimeOutFields,
    "nursing_intraoperative": NursingIntraoperativeFields,
    "nursing_sign_out": NursingSignOutFields,
    "anesthesia_pre_evaluation_plan": AnesthesiaPreEvaluationPlanFields,
    "anesthesia_induction_intraoperative": AnesthesiaInductionIntraoperativeFields,
    "anesthesia_observation_drugs": AnesthesiaObservationDrugsFields,
    "operative_note": OperativeNoteFields,
}
