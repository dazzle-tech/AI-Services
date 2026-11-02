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
    ocr_preprocess: bool = True
    ocr_try_rotations_on_low_quality: bool = True
    ocr_rotations_degrees: str = "0,90,180,270"
    ocr_min_avg_confidence: float = 0.35
    ocr_low_confidence_threshold: float = 0.20
    ocr_low_confidence_fraction_threshold: float = 0.55
    ocr_min_lines: int = 3
    ocr_min_image_short_side_px: int = 600
    ocr_min_blur_variance: float = 80.0
    ocr_brightness_min: float = 35.0
    ocr_brightness_max: float = 220.0
    ocr_contrast_std_min: float = 18.0
    ocr_return_boxes: bool = True
    ocr_use_model_confidence_for_quality: bool = False
    ocr_field_high_confidence: float = 0.90
    ocr_field_medium_confidence: float = 0.70

    # Identity extraction
    identity_llm_fallback_enabled: bool = False

    # Structured extraction/OpenAI
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"
    openai_vision_model: str = ""
    openai_vision_timeout: int = 30
    openai_vision_detail: str = "high"
    openai_temperature: float = 0.1
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0

    @property
    def vision_model(self) -> str:
        return self.openai_vision_model.strip() or self.openai_model

    @property
    def vision_detail(self) -> str:
        detail = (self.openai_vision_detail or "high").strip().lower()
        return detail if detail in {"low", "auto", "high"} else "high"

    @property
    def ocr_languages_list(self) -> list[str]:
        languages = [language.strip() for language in self.ocr_languages.split(",") if language.strip()]
        return languages or ["en"]

    @property
    def ocr_rotations_list(self) -> list[int]:
        out: list[int] = []
        for part in (self.ocr_rotations_degrees or "").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(part))
            except ValueError:
                continue
        return out or [0]


settings = Settings()
