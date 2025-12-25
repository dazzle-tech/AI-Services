"""
Quick API test script for medication-test-orders-validation service
"""
import requests
import json
from services.sample_clinical_data import MEDICATION_SAMPLES, TEST_SAMPLES

BASE_URL = "http://localhost:8000"

def test_medication_validation():
    """Test medication validation endpoint"""
    print("=" * 80)
    print("TESTING MEDICATION VALIDATION ENDPOINT")
    print("=" * 80)
    
    url = f"{BASE_URL}/api/v1/validate/medication"
    
    # Use first sample
    sample = MEDICATION_SAMPLES[0]
    
    print(f"\nTesting with patient: {sample['patient']['fullName']}")
    print(f"MRN: {sample['patient']['mrn']}")
    print(f"Age: {sample['encounter']['patientAge']}")
    print(f"Medications: {len(sample['medications'])}")
    
    try:
        print("\nSending request...")
        response = requests.post(url, json=sample, timeout=120)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n[OK] Validation successful!")
            print(f"\nOverall Status: {result['quick_summary']['overall_status']}")
            print(f"Top Priority: {result['quick_summary']['top_priority']}")
            print(f"Confidence Score: {result['confidence_score']:.2%}")
            
            if result['detailed_validations']:
                print(f"\nFound {len(result['detailed_validations'])} validation issues:")
                for i, val in enumerate(result['detailed_validations'][:3], 1):
                    print(f"\n{i}. {val['item']}")
                    print(f"   Severity: {val['severity']}")
                    print(f"   Issue: {val['issue']}")
                    print(f"   Recommendation: {val['recommendation']}")
            
            print("\n" + "=" * 80)
            print("FULL RESPONSE (first 500 chars):")
            print("=" * 80)
            print(json.dumps(result, indent=2)[:500] + "...")
            
            return True
        else:
            print(f"\n[ERROR] Error: {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_test_validation():
    """Test diagnostic test validation endpoint"""
    print("\n" + "=" * 80)
    print("TESTING TEST VALIDATION ENDPOINT")
    print("=" * 80)
    
    url = f"{BASE_URL}/api/v1/validate/tests"
    
    # Use first sample
    sample = TEST_SAMPLES[0]
    
    print(f"\nTesting with patient: {sample['patient']['fullName']}")
    print(f"MRN: {sample['patient']['mrn']}")
    print(f"Age: {sample['encounter']['patientAge']}")
    print(f"Tests: {len(sample['tests'])}")
    
    try:
        print("\nSending request...")
        response = requests.post(url, json=sample, timeout=120)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n[OK] Validation successful!")
            print(f"\nOverall Status: {result['quick_summary']['overall_status']}")
            print(f"Top Priority: {result['quick_summary']['top_priority']}")
            print(f"Confidence Score: {result['confidence_score']:.2%}")
            
            if result['detailed_validations']:
                print(f"\nFound {len(result['detailed_validations'])} validation issues:")
                for i, val in enumerate(result['detailed_validations'][:3], 1):
                    print(f"\n{i}. {val['item']}")
                    print(f"   Severity: {val['severity']}")
                    print(f"   Issue: {val['issue']}")
                    print(f"   Recommendation: {val['recommendation']}")
            
            print("\n" + "=" * 80)
            print("FULL RESPONSE (first 500 chars):")
            print("=" * 80)
            print(json.dumps(result, indent=2)[:500] + "...")
            
            return True
        else:
            print(f"\n[ERROR] Error: {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_health():
    """Test health endpoint"""
    print("=" * 80)
    print("TESTING HEALTH ENDPOINT")
    print("=" * 80)
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"[ERROR] Error: {str(e)}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("MEDICATION TEST ORDERS VALIDATION - API TESTING")
    print("=" * 80)
    
    # Test health first
    health_ok = test_health()
    
    if health_ok:
        # Test medication validation
        med_ok = test_medication_validation()
        
        # Test test validation
        test_ok = test_test_validation()
        
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Health Check: {'[PASS]' if health_ok else '[FAIL]'}")
        print(f"Medication Validation: {'[PASS]' if med_ok else '[FAIL]'}")
        print(f"Test Validation: {'[PASS]' if test_ok else '[FAIL]'}")
    else:
        print("\n[ERROR] Service is not healthy. Please check if the service is running.")

