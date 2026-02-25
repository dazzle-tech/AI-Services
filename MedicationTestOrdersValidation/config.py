from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings and configuration"""
    
    # API Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8006
    DEBUG: bool = True
    API_RELOAD: bool = False
    
    # OpenAI Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = "gpt-4o"  # or "gpt-4-turbo"
    OPENAI_TEMPERATURE: float = 0.2
    OPENAI_MAX_TOKENS: int = 2000
    
    # Validation Settings
    VALIDATION_CONFIDENCE_THRESHOLD: float = 0.7
    MAX_RETRY_ATTEMPTS: int = 3
    REQUEST_TIMEOUT: int = 60  # seconds
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True


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