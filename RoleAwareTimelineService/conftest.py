"""Test bootstrap. Sets service settings before the app is imported."""
import os

if not os.environ.get("OPENAI_API_KEY", "").strip():
    os.environ["OPENAI_API_KEY"] = "sk-test-key-for-testing-only"
if not os.environ.get("OPENAI_MODEL", "").strip():
    os.environ["OPENAI_MODEL"] = "test-model"
if not os.environ.get("OPENAI_BASE_URL", "").strip():
    os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
os.environ["OPENAI_RETRY_DELAY"] = "0"
os.environ.setdefault("OPENAI_TEMPERATURE", "0")
os.environ.setdefault("OPENAI_MAX_RETRIES", "2")
os.environ["OPENAI_TIMEOUT"] = "1"
os.environ.setdefault("API_PORT", "8040")
os.environ.setdefault("LOG_LEVEL", "INFO")
