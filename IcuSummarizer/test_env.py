"""Test script to verify .env file is loading correctly"""
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

print("=" * 50)
print("Testing .env file loading")
print("=" * 50)

api_key = os.getenv("OPENAI_API_KEY")
model_name = os.getenv("OPENAI_MODEL", "")

print(f"\nOPENAI_API_KEY: {'[OK] Loaded' if api_key else '[ERROR] Not found'}")
if api_key:
    print(f"  Key preview: {api_key[:20]}...{api_key[-10:]}")
else:
    print("  ERROR: OPENAI_API_KEY not found in .env file")

print(f"\nOPENAI_MODEL: {model_name}")

# Test app initialization
print("\n" + "=" * 50)
print("Testing app initialization")
print("=" * 50)

try:
    from app.main import app, openai_client
    
    print("\n[OK] App loaded successfully!")
    
    if openai_client:
        print("[OK] OpenAI client initialized successfully!")
        print(f"  Model: {openai_client.model_name}")
        print("\n[SUCCESS] Everything is working! You can now test the API endpoints.")
    else:
        print("\n[ERROR] OpenAI client NOT initialized")
        print("  This means OPENAI_API_KEY was not found or invalid")
        
except Exception as e:
    print(f"\n[ERROR] Error loading app: {e}")
    import traceback
    traceback.print_exc()
