"""Pydantic schemas for ORVoiceAgent."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

WindowRole = Literal["nurse", "anesthetist", "surgeon"]
ConfidenceLevel = Literal["high", "medium", "low"]


class AgentWindowJsonRequest(BaseModel):
    audio_base64: str
    filename: str = "audio.wav"
    role: Optional[str] = None


class TimeOutChecklistItem(BaseModel):
    key: str
    label: str
    checked: Optional[bool] = None
    note: str = ""


class TimeOutStaffMember(BaseModel):
    staffId: Optional[str] = None
    displayName: Optional[str] = None


class TimeOutStaff(BaseModel):
    surgeon: TimeOutStaffMember
    nurse: TimeOutStaffMember


class TimeOutResponse(BaseModel):
    checklist: List[TimeOutChecklistItem]
    staff: TimeOutStaff


class SignOutChecklistItem(BaseModel):
    key: str
    label: str
    checked: Optional[bool] = None
    response: Optional[str] = None
    note: str = ""


class SignOutResponse(BaseModel):
    checklist: List[SignOutChecklistItem]


class IntraoperativeOperationStaff(BaseModel):
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


class IntraoperativeAnesthesia(BaseModel):
    type: Optional[str] = None


class IntraoperativePosition(BaseModel):
    position: Optional[str] = None
    note: str = ""


class IntraoperativeSkinPreparation(BaseModel):
    preparationSkinWith: Optional[str] = None
    incisionSite: Optional[str] = None


class IntraoperativeFoleyCatheter(BaseModel):
    na: Optional[bool] = None
    catheterSize: Optional[int] = None
    urineOutputCc: Optional[int] = None
    color: Optional[str] = None


class IntraoperativeTourniquet(BaseModel):
    na: Optional[bool] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    totalDurationMinutes: Optional[int] = None
    pressureMmHg: Optional[int] = None
    site: Optional[str] = None


class IntraoperativeDiathermia(BaseModel):
    na: Optional[bool] = None
    electroSurgicalUnit: Optional[str] = None
    dispersiveElectrodeSite: Optional[str] = None
    electroRangeCutting: Optional[str] = None
    electroRangeCoagulation: Optional[str] = None
    skinConditionBefore: Optional[str] = None
    skinConditionAfter: Optional[str] = None
    note: str = ""


class IntraoperativeLaser(BaseModel):
    na: Optional[bool] = None
    pulseEnergy: Optional[str] = None
    frequency: Optional[str] = None
    stoneEffect: Optional[str] = None
    laserFiber: Optional[str] = None
    note: str = ""


class IntraoperativeDrainEntry(BaseModel):
    type: Optional[str] = None
    numberOfDrains: Optional[int] = None
    location: Optional[str] = None
    size: Optional[int] = None
    otherLabel: Optional[str] = None


class IntraoperativeDrains(BaseModel):
    na: Optional[bool] = None
    entries: List[IntraoperativeDrainEntry] = Field(default_factory=list)


class IntraoperativeSpecimenEntry(BaseModel):
    type: Optional[str] = None
    numberOfSamples: Optional[int] = None
    location: Optional[str] = None
    otherLabel: Optional[str] = None
    description: Optional[str] = None


class IntraoperativeSpecimens(BaseModel):
    na: Optional[bool] = None
    entries: List[IntraoperativeSpecimenEntry] = Field(default_factory=list)


class IntraoperativeResponse(BaseModel):
    operationStaff: IntraoperativeOperationStaff
    anesthesia: IntraoperativeAnesthesia
    position: IntraoperativePosition
    skinPreparationAndIncision: IntraoperativeSkinPreparation
    foleyCatheter: IntraoperativeFoleyCatheter
    tourniquet: IntraoperativeTourniquet
    diathermiaAndLaser: IntraoperativeDiathermia
    laser: IntraoperativeLaser
    drains: IntraoperativeDrains
    specimens: IntraoperativeSpecimens


class PreEvaluationSocialHistory(BaseModel):
    allergies: Optional[str] = None
    smoker: Optional[str] = None
    alcoholic: Optional[str] = None
    substanceUse: Optional[str] = None


class PreEvaluationLastMeal(BaseModel):
    food: Optional[str] = None
    foodDate: Optional[str] = None
    fluid: Optional[str] = None
    fluidDate: Optional[str] = None


class PreEvaluationPreviousAnesthesia(BaseModel):
    previousAnesthesia: Optional[str] = None
    previousSurgery: Optional[str] = None
    difficultIntubation: Optional[str] = None
    complication: Optional[str] = None
    comments: Optional[str] = None


class PreEvaluationPastMedicalHistory(BaseModel):
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


class PreEvaluationVitalSigns(BaseModel):
    weightKg: Optional[float] = None
    bpSystolic: Optional[int] = None
    bpDiastolic: Optional[int] = None
    pulseRate: Optional[int] = None
    tempC: Optional[float] = None
    spo2: Optional[int] = None


class PreEvaluationClinicalExamination(BaseModel):
    cardiovascular: str = ""
    respiratory: str = ""
    skin: str = ""
    sensors: str = ""
    neuromuscular: str = ""
    gcs: Optional[int] = None
    others: str = ""


class PreEvaluationAirwayAssessment(BaseModel):
    openMouth: str = ""
    thyromentalDistance: str = ""
    neckMobility: str = ""
    others: str = ""


class PreEvaluationClinicalData(BaseModel):
    chestXray: str = ""
    ecg: str = ""
    others: str = ""


class PreEvaluationAsa(BaseModel):
    asaClass: Optional[str] = None
    emergency: Optional[bool] = None


class PreEvaluationOrders(BaseModel):
    orders: Optional[str] = None


class PreEvaluationPreMedication(BaseModel):
    preMedication: Optional[str] = None
    prophylacticAntibiotic: Optional[str] = None
    prophylacticAntibioticNote: Optional[str] = None


class PreEvaluationPlanResponse(BaseModel):
    socialHistory: PreEvaluationSocialHistory
    lastMeal: PreEvaluationLastMeal
    previousAnesthesiaAndSurgery: PreEvaluationPreviousAnesthesia
    pastMedicalHistory: PreEvaluationPastMedicalHistory
    vitalSigns: PreEvaluationVitalSigns
    clinicalExamination: PreEvaluationClinicalExamination
    airwayAssessment: PreEvaluationAirwayAssessment
    clinicalData: PreEvaluationClinicalData
    asa: PreEvaluationAsa
    preAnesthesiaOrders: PreEvaluationOrders
    preMedication: PreEvaluationPreMedication


class InductionPreAssessment(BaseModel):
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


class InductionIntraoperativeAnesthesia(BaseModel):
    induction: Optional[str] = None
    intubation: Optional[str] = None
    airway: Optional[str] = None
    position: Optional[str] = None
    anesthesiologistResident: Optional[str] = None
    anesthesiaTechnician: Optional[str] = None


class InductionIntraoperativeResponse(BaseModel):
    preInductionAssessment: InductionPreAssessment
    intraoperativeAnesthesia: InductionIntraoperativeAnesthesia


class ObservationVitalSign(BaseModel):
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


class ObservationBloodLoss(BaseModel):
    bloodQuantity: str = ""
    bloodLoss: Optional[int] = None


class ObservationDrugsResponse(BaseModel):
    vitalSign: ObservationVitalSign
    bloodLoss: ObservationBloodLoss


class OperativeNoteDetails(BaseModel):
    time: Optional[str] = None
    typeOfAnesthesia: Optional[str] = None


class OperativeNoteStaff(BaseModel):
    mainSurgeon: Optional[str] = None
    surgeonsAssistant: Optional[str] = None
    surgicalStartTime: Optional[str] = None
    surgicalEndTime: Optional[str] = None


class OperativeNoteResponse(BaseModel):
    operativeDetails: OperativeNoteDetails
    operationStaff: OperativeNoteStaff
    operationNote: Optional[str] = None
    complication: Optional[str] = None
    estimatedBloodLossMl: Optional[int] = None


class WindowExtractResponse(BaseModel):
    """Same shape as ORDisplayPlugin window fill — this is the EMR final payload."""

    case_id: str
    window_id: str
    fields: Dict[str, Any]
    confidence: ConfidenceLevel
    needs_review: bool
    missing_fields: List[str] = Field(default_factory=list)
    raw_text: str


class DownstreamHealth(BaseModel):
    orscribe: str
    ordisplay_plugin: str


class HealthResponse(BaseModel):
    status: str
    downstream: DownstreamHealth
    details: Dict[str, Any] = Field(default_factory=dict)
