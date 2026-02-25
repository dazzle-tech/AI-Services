"""Configuration for OCR Parsing Service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
    )

    # API
    api_title: str = "OCR Parsing Service"
    api_version: str = "1.0.0"
    api_description: str = "Extract text from images and parse into structured JSON"
    api_host: str = "0.0.0.0"
    api_port: int = 8012
    api_reload: bool = False

    # OCR
    ocr_languages: str = "en"
    ocr_gpu: bool = False

    # Parsing/Ollama
    ollama_command: str = "ollama"
    ollama_model: str = "gemma3:4b"
    ollama_timeout_seconds: int = 120

    @property
    def ocr_languages_list(self) -> list[str]:
        languages = [language.strip() for language in self.ocr_languages.split(",") if language.strip()]
        return languages or ["en"]


settings = Settings()
