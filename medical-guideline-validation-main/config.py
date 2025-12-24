"""
Configuration for Medical Guideline Validation System
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.1"))

# Guidelines Storage
GUIDELINES_DIR = "data/guidelines"
VECTOR_STORE_PATH = "./vector_store_guidelines"

# API Configuration
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))
API_RELOAD = os.environ.get("API_RELOAD", "False").lower() == "true"

# Validation
if OPENAI_API_KEY:
    print(f"✅ OpenAI API Key loaded: {OPENAI_API_KEY[:15]}...{OPENAI_API_KEY[-4:]}")
else:
    print("⚠️  WARNING: OPENAI_API_KEY not found!")
    print("   Please add it to your .env file:")
    print("   OPENAI_API_KEY=sk-your-key-here")