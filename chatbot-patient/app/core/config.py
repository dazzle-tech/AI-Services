"""Configuration for the patient chatbot.

Self-contained for now. Phase 5 of the split moves the infrastructure pieces this
sits on top of into ``shared/medai-core/``; the settings names here are chosen to
match the clinician bot's so that move is mechanical.
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# chatbot-patient/app/core/config.py → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = Path(os.getenv("MEDAI_DATA_DIR", str(_REPO_ROOT / "data")))
_CHATBOT_DATA = Path(os.getenv("CHATBOT_DATA_DIR", str(_REPO_ROOT / "Chatbot" / "data")))
_ENV_FILE = _APP_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_title: str = "MedAI Patient Assistant"
    api_version: str = "1.0.0"
    api_description: str = (
        "Patient-facing conversational agent. Answers about the patient's own record, "
        "their appointments, and general hospital information."
    )

    # ---- LLM (one shared OpenAI-compatible endpoint, as everywhere else) ----
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"          # routing / classification: fast + cheap
    reasoning_model: str = "gpt-4.1"           # user-facing answers
    openai_timeout: int = 60
    openai_max_retries: int = 1

    # ---- Redis session store ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    session_ttl_seconds: int = 86400

    # ---- Tools ----
    # Which services the patient agent may call comes from Services.txt [PATIENT].
    medai_services_file: str = "/app/Services.txt"
    medai_tools_host: str = ""                 # set to "localhost" to run outside compose
    tool_timeout_seconds: float = 20.0

    # ---- Prompts ----
    medai_prompts_file: str = "/app/Prompts_patient.md"

    # ---- Server ----
    api_host: str = "0.0.0.0"
    api_port: int = 8030
    api_reload: bool = False

    log_level: str = "INFO"

    # ---- Hospital data (phone → patient_id for WhatsApp) ----
    medai_data_dir: str = str(_DATA_DIR)
    # Asklepios schema / access policy live with the original Chatbot.
    chatbot_data_dir: str = str(_CHATBOT_DATA)
    schema_graph_path: str = str(_CHATBOT_DATA / "schema_graph.json")
    access_control_path: str = str(_CHATBOT_DATA / "access_control.json")
    hospital_db_path: str = str(_DATA_DIR / "hospital.db")
    registered_users_db_path: str = str(_DATA_DIR / "registered_users.db")
    # Same PostgreSQL as Chatbot/app/core/config.py (overridable via .env)
    db_type: str = "postgresql"
    db_host: str = "161.35.195.29"
    db_port: int = 5432
    db_name: str = "asklepios-demo"
    db_user: str = "asklepios-dev"
    db_password: str = ""
    db_schema: str = "public"

    # ---- Registration / WhatsApp identity ----
    default_phone_country_code: str = "+1"
    hospital_admin_contact: str = "your hospital IT administrator"
    # Optional JSON: {"15551234567": 1005} — maps a WhatsApp number to patients.patient_id
    whatsapp_patient_map: str = ""

    # ---- WhatsApp Business Cloud API (same names as the clinician bot) ----
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_pipeline_timeout_secs: int = 30
    whatsapp_max_message_length: int = 4096

    @property
    def prompts_path(self) -> Path:
        return Path(self.medai_prompts_file)

    @property
    def services_path(self) -> Path:
        return Path(self.medai_services_file)

    @property
    def whatsapp_configured(self) -> bool:
        return bool(
            self.whatsapp_access_token
            and self.whatsapp_phone_number_id
            and self.whatsapp_app_secret
            and self.whatsapp_verify_token
        )


settings = Settings()


def _resolve_app_path(path: str) -> str:
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str((_APP_ROOT / p).resolve())


settings.chatbot_data_dir = _resolve_app_path(settings.chatbot_data_dir)
settings.schema_graph_path = _resolve_app_path(settings.schema_graph_path)
settings.access_control_path = _resolve_app_path(settings.access_control_path)
settings.hospital_db_path = _resolve_app_path(settings.hospital_db_path)

# `MEDAI_TOOLS_HOST` is read directly by the tool registry too; keep them consistent.
if settings.medai_tools_host:
    os.environ.setdefault("MEDAI_TOOLS_HOST", settings.medai_tools_host)
