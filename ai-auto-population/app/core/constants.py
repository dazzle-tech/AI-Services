"""Constants for the AI Auto-Population Service."""
from enum import Enum


class UserRole(str, Enum):
    """User roles with access levels."""
    DOCTOR = "doctor"
    NURSE = "nurse"
    ADMIN = "admin"


class TaskType(str, Enum):
    """Supported task types."""
    AUTO_POPULATION = "auto_population"
    # Future: DISCHARGE_QA = "discharge_qa"
    # Future: GUIDELINE_CHECK = "guideline_check"
    # Future: RECOMMENDATIONS = "recommendations"


class SupportedLanguage(str, Enum):
    """Supported input/output languages."""
    EN = "en"
    ES = "es"
    FR = "fr"
    DE = "de"


# Role-based field access restrictions
ROLE_FIELD_RESTRICTIONS = {
    UserRole.DOCTOR: [],  # Doctors can access all fields
    UserRole.NURSE: ["diagnosis", "procedures"],  # Nurses cannot access these
    UserRole.ADMIN: ["diagnosis", "medications", "procedures", "vitals"]  # Admins have limited access
}

