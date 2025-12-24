"""
Configuration for Medical Guideline Validation System
"""

import os
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

logger.info("Environment variables loaded from .env file")

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.1"))

# Guidelines Storage
GUIDELINES_DIR = os.environ.get("GUIDELINES_DIR", "data/guidelines")
VECTOR_STORE_PATH = os.environ.get("VECTOR_STORE_PATH", "./vector_store_guidelines")

# API Configuration
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))
API_RELOAD = os.environ.get("API_RELOAD", "False").lower() == "true"

# CORS Configuration
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
# Parse comma-separated origins or use "*" for all
if CORS_ORIGINS and CORS_ORIGINS != "*":
    CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS.split(",")]
else:
    CORS_ORIGINS = ["*"]  # Default to all for development

# Validation
if OPENAI_API_KEY:
    logger.info("OpenAI API Key loaded successfully")
else:
    logger.warning("OPENAI_API_KEY not found! Please add it to your .env file")