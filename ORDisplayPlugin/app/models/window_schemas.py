# TODO: reconcile with real EMR/UI field names

"""Placeholder clinical field schemas for the eight OR window/sub-tab screens.

Every field is Optional — a single dictation will not cover the full window.

LLM outputs often mistype values (numbers for string fields, unit-suffixed strings
for numerics, "" for missing ints). `_WindowFields` coerces those before validation
so all window endpoints share the same tolerance.
"""

from __future__ import annotations

import re
import types
from typing import Any, List, Literal, Optional, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, model_validator

_NUMERIC_TOKEN = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)")


def _coerce_optional_float(value: object) -> float | None:
    """Accept bare numbers or unit-suffixed strings like '82 kg' / '36.8 C'."""
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = _NUMERIC_TOKEN.search(text)
    if not match:
        return None
    return float(match.group(0))


def _coerce_optional_int(value: object) -> int | None:
    parsed = _coerce_optional_float(value)
    if parsed is None:
        return None
    return int(round(parsed))


def _coerce_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _unwrap_optional(annotation: object) -> tuple[object, bool]:
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def _is_basemodel_type(annotation: object) -> bool:
    try:
        return isinstance(annotation, type) and issubclass(annotation, BaseModel)
    except TypeError:
        return False


def _coerce_scalar(value: object, annotation: object, *, optional: bool) -> object:
    origin = get_origin(annotation)

    if origin in (list, List) or _is_basemodel_type(annotation):
        return value

    if origin is Literal:
        if value is None:
            return None if optional else value
        # Prefer string form for string literals (e.g. status enums).
        literal_args = get_args(annotation)
        if literal_args and all(isinstance(arg, str) for arg in literal_args):
            return str(value)
        return value

    if annotation is str:
        if value is None:
            return None if optional else ""
        return str(value)

    if annotation is int:
        return _coerce_optional_int(value)

    if annotation is float:
        return _coerce_optional_float(value)

    if annotation is bool:
        return _coerce_optional_bool(value)

    return value


def _coerce_llm_payload(cls: type[BaseModel], data: object) -> object:
    if not isinstance(data, dict):
        return data
    coerced: dict[str, Any] = dict(data)
    for name, field in cls.model_fields.items():
        if name not in coerced:
            continue
        inner, optional = _unwrap_optional(field.annotation)
        coerced[name] = _coerce_scalar(coerced[name], inner, optional=optional)
    return coerced


class _WindowFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_types(cls, data: object) -> object:
        return _coerce_llm_payload(cls, data)


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


class LaserBlock(_WindowFields):
    na: Optional[bool] = None
    pulseEnergy: Optional[str] = None
    frequency: Optional[str] = None
    stoneEffect: Optional[str] = None
    laserFiber: Optional[str] = None
    note: str = ""


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


class SocialHistory(_WindowFields):
    allergies: Optional[str] = None
    smoker: Optional[str] = None
    alcoholic: Optional[str] = None
    substanceUse: Optional[str] = None


class LastMeal(_WindowFields):
    food: Optional[str] = None
    foodDate: Optional[str] = None
    fluid: Optional[str] = None
    fluidDate: Optional[str] = None


class PreviousAnesthesiaAndSurgery(_WindowFields):
    previousAnesthesia: Optional[str] = None
    previousSurgery: Optional[str] = None
    difficultIntubation: Optional[str] = None
    complication: Optional[str] = None
    comments: Optional[str] = None


class PastMedicalHistory(_WindowFields):
    cardiovascular: str = ""
    respiratory: str = ""
    neurological: str = ""
    urological: str = ""
    musculoskeletal: str = ""
    psychiatric: str = ""
    pregnancies: str = ""
    renalDisease: str = ""
    endocrine: str = ""
    hepatic: str = ""
    gastrointestinal: str = ""
    bloodVessel: str = ""
    otherDiseases: str = ""


class PreEvalVitalSigns(_WindowFields):
    weightKg: Optional[float] = None
    bpSystolic: Optional[int] = None
    bpDiastolic: Optional[int] = None
    pulseRate: Optional[int] = None
    tempC: Optional[float] = None
    spo2: Optional[int] = None


class ClinicalExamination(_WindowFields):
    cardiovascular: str = ""
    respiratory: str = ""
    skin: str = ""
    sensors: str = ""
    neuromuscular: str = ""
    gcs: Optional[int] = None
    others: str = ""


class AirwayAssessment(_WindowFields):
    mallampatiClass: str = ""
    openMouth: str = ""
    thyromentalDistance: str = ""
    dentalState: str = ""
    neckMobility: str = ""
    others: str = ""


class ClinicalData(_WindowFields):
    chestXray: str = ""
    ecg: str = ""
    others: str = ""


class AsaBlock(_WindowFields):
    asaClass: Optional[str] = None
    emergency: Optional[bool] = None


class PreAnesthesiaOrders(_WindowFields):
    orders: Optional[str] = None


class PreMedication(_WindowFields):
    preMedication: Optional[str] = None
    prophylacticAntibiotic: Optional[str] = None
    prophylacticAntibioticNote: Optional[str] = None


class AnesthesiaPlan(_WindowFields):
    typeOfAnesthesia: str = ""
    anesthesiologist: str = ""
    anesthesiologistResident: str = ""
    date: Optional[str] = None


class AnesthesiaPreEvaluationPlanFields(_WindowFields):
    socialHistory: Optional[SocialHistory] = None
    lastMeal: Optional[LastMeal] = None
    previousAnesthesiaAndSurgery: Optional[PreviousAnesthesiaAndSurgery] = None
    pastMedicalHistory: Optional[PastMedicalHistory] = None
    vitalSigns: Optional[PreEvalVitalSigns] = None
    clinicalExamination: Optional[ClinicalExamination] = None
    airwayAssessment: Optional[AirwayAssessment] = None
    clinicalData: Optional[ClinicalData] = None
    asa: Optional[AsaBlock] = None
    preAnesthesiaOrders: Optional[PreAnesthesiaOrders] = None
    preMedication: Optional[PreMedication] = None
    anesthesiaPlan: Optional[AnesthesiaPlan] = None


class PreInductionAssessment(_WindowFields):
    bpSystolic: Optional[int] = None
    bpDiastolic: Optional[int] = None
    hr: Optional[int] = None
    rr: Optional[int] = None
    o2Sat: Optional[int] = None
    npo: Optional[str] = None
    npoDate: Optional[str] = None
    preMedication: Optional[str] = None
    preMedicationNote: Optional[str] = None
    date: Optional[str] = None


class IntraoperativeAnesthesia(_WindowFields):
    induction: Optional[str] = None
    intubation: Optional[str] = None
    airway: Optional[str] = None
    position: Optional[str] = None
    anesthesiologistResident: Optional[str] = None
    anesthesiaTechnician: Optional[str] = None


class AnesthesiaInductionIntraoperativeFields(_WindowFields):
    preInductionAssessment: Optional[PreInductionAssessment] = None
    intraoperativeAnesthesia: Optional[IntraoperativeAnesthesia] = None


class ObservationVitalSign(_WindowFields):
    bpSystolic: Optional[int] = None
    bpDiastolic: Optional[int] = None
    hr: Optional[int] = None
    oxygenSupply: str = ""
    etco2: Optional[int] = None
    spo2: Optional[int] = None
    tempC: str = ""
    tidalVolume: str = ""
    rr: str = ""
    act: str = ""
    fio2: str = ""
    rbs: str = ""
    o2Air: str = ""


class ObservationBloodLoss(_WindowFields):
    bloodQuantity: str = ""
    bloodLoss: Optional[int] = None


class AnesthesiaObservationDrugsFields(_WindowFields):
    vitalSign: Optional[ObservationVitalSign] = None
    bloodLoss: Optional[ObservationBloodLoss] = None


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
