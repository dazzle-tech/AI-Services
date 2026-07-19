"""Constants for the AI Auto-Population Service."""
from enum import Enum


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


