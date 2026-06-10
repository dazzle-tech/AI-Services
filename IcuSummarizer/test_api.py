"""Simple test script for ICU Summarizer API"""
import requests
import json
import sys

BASE_URL = "http://localhost:8013"

def test_summaries():
    """Test summaries endpoint"""
    print("\nTesting POST /v1/summaries...")
    try:
        with open("test_sample_request.json", "r") as f:
            payload = json.load(f)
        
        response = requests.post(
            f"{BASE_URL}/v1/summaries",
            json=payload,
            headers={"X-Request-ID": "test-123", "Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code}")
        print(f"Request ID: {response.headers.get('X-Request-ID')}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Note JSON keys: {list(data.get('note_json', {}).keys())}")
            print(f"Warnings: {len(data.get('warnings', []))}")
            print(f"Source counts: {data.get('source_counts')}")
            print(f"Note markdown preview (first 200 chars): {data.get('note_markdown', '')[:200]}...")
            return True
        else:
            print(f"Error response: {response.text}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("ICU Summarizer API Test")
    print("=" * 50)
    
    # Test summaries (this requires OpenAI API key)
    summaries_ok = test_summaries()
    
    if summaries_ok:
        print("\n[PASS] All tests passed!")
    else:
        print("\n[FAIL] Some tests failed")
        sys.exit(1)
