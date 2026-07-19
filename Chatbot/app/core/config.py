"""Configuration management for MedAI Assistant services."""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra environment variables that don't match fields
    )
    
    # Service URLs
    sql_gen_url: str = os.getenv("SQL_GEN_URL", "http://localhost:8018")
    validator_url: str = os.getenv("VALIDATOR_URL", "http://localhost:8019")
    formatter_url: str = os.getenv("FORMATTER_URL", "http://localhost:8020")
    http_timeout_secs: int = int(os.getenv("HTTP_TIMEOUT_SECS", "90"))  # Increased for CrewAI processing
    
    # CrewAI Configuration
    use_crewai: bool = os.getenv("USE_CREWAI", "false").lower() == "true"  # Disable CrewAI by default for faster responses
    
    # LLM Configuration
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" or "openai"
    
    # Ollama Configuration
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    llm_model: str = os.getenv("LLM_MODEL", "") or os.getenv("OPENAI_MODEL", "")
    sql_gen_model: str = os.getenv("SQL_GEN_MODEL", "") or os.getenv("OPENAI_MODEL", "")
    
    # OpenAI Configuration
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "")
    openai_sql_gen_model: str = os.getenv("OPENAI_SQL_GEN_MODEL", "") or os.getenv("OPENAI_MODEL", "")
    openai_timeout: int = int(os.getenv("OPENAI_TIMEOUT", "120"))
    openai_max_retries: int = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
    
    # Database Configuration
    # Database Type: "sqlite" or "postgresql"
    db_type: str = os.getenv("DB_TYPE", "sqlite")
    
    # SQLite Database Paths (used when db_type="sqlite")
    hospital_db_path: str = os.getenv("HOSPITAL_SQLITE_PATH", "data/hospital.db")
    audit_db_path: str = os.getenv("AUDIT_DB_PATH", "data/medai_audit.db")
    
    # PostgreSQL Configuration (used when db_type="postgresql")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "DBLocal")
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "123456")
    db_schema: str = os.getenv("DB_SCHEMA", "public")
    
    # Configuration File Paths
    access_control_path: str = os.getenv("ACCESS_CONTROL_PATH", "data/access_control.json")
    schema_graph_path: str = os.getenv("SCHEMA_GRAPH_PATH", "data/schema_graph.json")
    sessions_memory_path: str = os.getenv("SESSIONS_MEMORY_PATH", "data/sessions_memory.json")
    
    # Redis Configuration (for session memory)
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "86400"))  # 24 hours
    
    # Audit Configuration
    audit_max_row_preview: int = int(os.getenv("AUDIT_MAX_ROW_PREVIEW", "10"))
    audit_store_full_rows: bool = os.getenv("AUDIT_STORE_FULL_ROWS", "0") == "1"
    
    # Server Configuration
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    orchestrator_port: int = int(os.getenv("ORCHESTRATOR_PORT", "8017"))
    sql_generator_port: int = int(os.getenv("SQL_GENERATOR_PORT", "8018"))
    validator_port: int = int(os.getenv("VALIDATOR_PORT", "8019"))
    formatter_port: int = int(os.getenv("FORMATTER_PORT", "8020"))
    api_reload: bool = os.getenv("API_RELOAD", "true").lower() == "true"  # Default to True for development
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Web authentication (Phase 1)
    # JSON map: {"token-value": "user_id"} — never commit real production tokens
    web_auth_tokens: str = os.getenv("WEB_AUTH_TOKENS", "")
    web_auth_dev_mode: bool = os.getenv("WEB_AUTH_DEV_MODE", "false").lower() == "true"
    internal_service_token: str = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    environment: str = os.getenv("ENVIRONMENT", "development")

    # Rate limiting (Phase 1)
    rate_limit_max_requests: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "60"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Registration / WhatsApp (Phase 2–3)
    registered_users_db_path: str = os.getenv("REGISTERED_USERS_DB_PATH", "data/registered_users.db")
    default_phone_country_code: str = os.getenv("DEFAULT_PHONE_COUNTRY_CODE", "+1")
    hospital_admin_contact: str = os.getenv("HOSPITAL_ADMIN_CONTACT", "your hospital IT administrator")
    otp_ttl_seconds: int = int(os.getenv("OTP_TTL_SECONDS", "600"))
    otp_length: int = int(os.getenv("OTP_LENGTH", "6"))

    # WhatsApp Business Cloud API (Phase 3)
    whatsapp_adapter_port: int = int(os.getenv("WHATSAPP_ADAPTER_PORT", "8021"))
    whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    whatsapp_app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")
    whatsapp_access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_api_version: str = os.getenv("WHATSAPP_API_VERSION", "v21.0")
    orchestrator_url: str = os.getenv("ORCHESTRATOR_URL", "http://localhost:8017")
    whatsapp_pipeline_timeout_secs: int = int(os.getenv("WHATSAPP_PIPELINE_TIMEOUT_SECS", "15"))
    whatsapp_max_message_length: int = int(os.getenv("WHATSAPP_MAX_MESSAGE_LENGTH", "4096"))

    # EMR / pharmacy API (Phase 4 — stub until vendor contract is finalized)
    emr_api_base_url: str = os.getenv("EMR_API_BASE_URL", "")
    emr_api_key: str = os.getenv("EMR_API_KEY", "")

    # Confirmation tokens for write actions (Phase 4)
    confirmation_token_ttl_seconds: int = int(os.getenv("CONFIRMATION_TOKEN_TTL_SECONDS", "300"))

    # Agent routing (Phase 4)
    use_agent_router: bool = os.getenv("USE_AGENT_ROUTER", "true").lower() == "true"


settings = Settings()

