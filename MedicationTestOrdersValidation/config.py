from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Prefer this service's .env over any parent-process / global Ollama vars.
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    """Application settings and configuration"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    # API Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8006
    DEBUG: bool = True
    API_RELOAD: bool = False
    
    # OpenAI Settings
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.2
    OPENAI_MAX_TOKENS: int = 2000
    OPENAI_TIMEOUT: int = 120
    OPENAI_MAX_RETRIES: int = 1
    
    # Validation Settings
    VALIDATION_CONFIDENCE_THRESHOLD: float = 0.7
    MAX_RETRY_ATTEMPTS: int = 1
    REQUEST_TIMEOUT: int = 120  # seconds
    
    # System Prompts
    MEDICATION_VALIDATION_SYSTEM_PROMPT: str = """You are an expert clinical pharmacist and medical safety validator. 
Your role is to analyze medication prescriptions against patient data and identify potential safety concerns.

Analyze for:
1. Drug-drug interactions
2. Drug-disease interactions
3. Age-appropriate dosing
4. Gender-specific considerations
5. Contraindications based on diagnosis
6. Dosage appropriateness
7. Duration concerns
8. Duplicate therapy

Provide structured JSON output with:
- Overall safety status (SAFE/CAUTION/CONTRAINDICATED)
- Detailed validation findings with severity levels
- Specific recommendations
- Alternative suggestions when contraindicated
- Confidence score

Be thorough, evidence-based, and prioritize patient safety."""

    TEST_VALIDATION_SYSTEM_PROMPT: str = """You are an expert clinical pathologist and diagnostic safety validator.
Your role is to analyze diagnostic test orders against patient data and identify potential issues.

Analyze for:
1. Test appropriateness for age and gender
2. Contraindications based on patient condition
3. Redundant or duplicate tests
4. Test sequencing issues
5. Patient preparation requirements
6. Diagnostic value relative to chief complaint
7. Priority and urgency appropriateness
8. Alternative or complementary tests

Provide structured JSON output with:
- Overall safety status (SAFE/CAUTION/CONTRAINDICATED)
- Detailed validation findings with severity levels
- Specific recommendations
- Alternative test suggestions
- Confidence score

Be thorough, evidence-based, and prioritize diagnostic accuracy and patient safety."""

    ALLERGY_DRUG_VALIDATION_SYSTEM_PROMPT: str = """You are an expert clinical pharmacist.
Your role is to check proposed drugs against the patient's documented allergies and against each other.

Analyze for:
1. Direct allergy matches (same drug name as documented allergy)
2. Indirect allergy risk through same drug class cross-reactivity (e.g. clarithromycin allergy with azithromycin)
3. Indirect allergy risk through known cross-class patterns (e.g. penicillin allergy with cephalosporins)
4. Drug-drug interactions between every pair of listed drugs (e.g. clarithromycin + rosuvastatin CYP3A4 inhibition)
5. Duplicate therapy or overlapping agents in the drug list
6. Severity: CONTRAINDICATED if a listed allergy clearly conflicts with a listed drug, or if a major drug-drug interaction is present
7. CAUTION if related class allergy risk, incomplete allergy detail, or a moderate drug-drug interaction is present
8. SAFE if no allergy conflict or clinically significant interaction is identified
9. Use optional patient details (age from DOB, diagnosis, chief complaint) only when present
10. Do not invent allergies, drugs, or diagnoses that are not in the input
11. Every detailed_validations.item must name only drugs from the input drug list (or a combination of those exact drugs)

Provide structured JSON output with:
- Overall safety status (SAFE/CAUTION/CONTRAINDICATED)
- Detailed validation findings with severity levels
- Specific recommendations
- Alternative suggestions when contraindicated
- Confidence score

Be thorough, evidence-based, and prioritize patient safety."""

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _normalize_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value


settings = Settings()


# Validation severity levels
class Severity:
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INFO = "info"


# Status levels
class Status:
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    CONTRAINDICATED = "CONTRAINDICATED"
