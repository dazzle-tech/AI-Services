"""
Configuration for the Radiology Template Selection & Autofill Service.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

# Load env vars from the project's .env regardless of the current working directory.
load_dotenv(dotenv_path=BASE_DIR / ".env")
logger.info("Environment variables loaded from .env file")

def _resolve_path(value: str) -> str:
    p = Path(value)
    if p.is_absolute():
        return str(p)
    return str((BASE_DIR / p).resolve())


# OpenAI
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "120"))
OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "1"))
OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.1"))

# Embeddings + vector store
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TEMPLATES_DIR = _resolve_path(os.environ.get("TEMPLATES_DIR", "data/templates"))
VECTOR_STORE_PATH = _resolve_path(os.environ.get("VECTOR_STORE_PATH", "vector_store_templates"))

# API
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8022"))
API_RELOAD = os.environ.get("API_RELOAD", "False").lower() == "true"

# CORS
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
if CORS_ORIGINS and CORS_ORIGINS != "*":
    CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS.split(",")]
else:
    CORS_ORIGINS = ["*"]

# Mock mode (skip OpenAI calls — useful for testing without an API key)
MOCK_LLM = os.environ.get("MOCK_LLM", "false").lower() == "true"

if OPENAI_API_KEY:
    logger.info("OpenAI API Key loaded successfully")
elif not MOCK_LLM:
    logger.warning("OPENAI_API_KEY not set and MOCK_LLM=false — autofill calls will fail")
