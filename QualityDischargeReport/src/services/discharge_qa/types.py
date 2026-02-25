"""Type definitions and enums for discharge QA."""

from enum import Enum


class Severity(str, Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Category(str, Enum):
    """Error categories."""
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    SAFETY = "safety"
    STRUCTURE = "structure"


class DocType(str, Enum):
    """Clinical document types."""
    HISTORY_AND_PHYSICAL = "history_and_physical"
    PROGRESS_NOTE = "progress_note"
    DISCHARGE_SUMMARY = "discharge_summary"
    CONSULT_NOTE = "consult_note"
    NURSING_NOTE = "nursing_note"
    RADIOLOGY_REPORT = "radiology_report"
    PATHOLOGY_REPORT = "pathology_report"
    LAB_REPORT = "lab_report"


class CorrectionAction(str, Enum):
    """Types of recommended corrections."""
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    REPHRASE = "rephrase"


class SourceType(str, Enum):
    """Source types for references."""
    PATIENT_RECORD = "patient_record"
    ONSITE_DOC = "onsite_doc"
    TEMPLATE = "template"
    QUALITY_RULE = "quality_rule"

