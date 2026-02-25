"""Error types for the application"""
from typing import Optional


class ICUSummarizerError(Exception):
    """Base exception for ICU Summarizer"""
    def __init__(self, message: str, code: Optional[str] = None):
        self.message = message
        self.code = code or "INTERNAL_ERROR"
        super().__init__(self.message)


class ValidationError(ICUSummarizerError):
    """Validation error"""
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class ExternalServiceError(ICUSummarizerError):
    """Error from external service (e.g., OpenAI)"""
    def __init__(self, message: str, service: str = "EXTERNAL_SERVICE"):
        super().__init__(message, code=f"{service}_ERROR")
        self.service = service


class ConfigurationError(ICUSummarizerError):
    """Configuration error"""
    def __init__(self, message: str):
        super().__init__(message, code="CONFIGURATION_ERROR")
