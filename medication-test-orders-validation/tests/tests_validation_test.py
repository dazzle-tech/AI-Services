import asyncio
import json
from services.medication_tests_validation_service import TestValidationService
from models.schemas import TestValidationRequest
from services.sample_clinical_data import TEST_SAMPLES


async def test_diagnostic_validation(sample_index: int = 0):
    """
    Test diagnostic test validation service with sample data
    
    Args:
        sample_index: Index of the sample to test (0-2)
    """
    print("=" * 80)
    print("DIAGNOSTIC TEST VALIDATION TEST")
    print("=" * 80)
    
    try:
        # Initialize service
        print("\n[1] Initializing Test Validation Service...")
        service = TestValidationService()
        print("✓ Service initialized successfully")
        
        # Load sample data
        print(f"\n[2] Loading sample data (Sample {sample_index + 1})...")
        sample_data = TEST_SAMPLES[sample_index]
        print(f"✓ Sample data loaded: Patient MRN {sample_data['patient']['mrn']}")
        
        # Create request
        print("\n[3] Creating validation request...")
        request = TestValidationRequest(**sample_data)
        print(f"✓ Request created for patient: {request.patient.fullName}")
        print(f"  - Age: {request.encounter.patientAge}")
        print(f"  - Chief Complaint: {request.encounter.chiefComplaint}")
        print(f"  - Diagnosis: {request.encounter.diagnosis}")
        print(f"  - Number of tests: {len(request.tests)}")
        
        # Display tests being validated
        print("\n[4] Tests to validate:")
        for i, test in enumerate(request.tests, 1):
            print(f"  {i}. {test[:100]}...")
        
        # Call validation service
        print("\n[5] Calling validation service...")
        print("  (This may take 10-30 seconds depending on OpenAI API response time)")
        
        result = await service.validate(request)
        
        print("✓ Validation completed successfully!")
        
        # Display results
        print("\n" + "=" * 80)
        print("VALIDATION RESULTS")
        print("=" * 80)
        
        print("\n[QUICK SUMMARY]")
        print(f"Overall Status: {result.quick_summary.overall_status}")
        print(f"Top Priority: {result.quick_summary.top_priority}")
        print(f"Confidence Score: {result.confidence_score:.2%}")
        
        if result.detailed_validations:
            print("\n[DETAILED VALIDATIONS]")
            for i, validation in enumerate(result.detailed_validations, 1):
                print(f"\n{i}. Item: {validation.item}")
                print(f"   Severity: {validation.severity.upper()}")
                print(f"   Issue: {validation.issue}")
                print(f"   Recommendation: {validation.recommendation}")
                if validation.evidence:
                    print(f"   Evidence: {validation.evidence}")
        else:
            print("\n[DETAILED VALIDATIONS]")
            print("No issues found")
        
        if result.recommended_alternatives:
            print("\n[RECOMMENDED ALTERNATIVES]")
            for i, alt in enumerate(result.recommended_alternatives, 1):
                print(f"\n{i}. Original: {alt.original_item}")
                print(f"   Alternative/Additional: {alt.alternative}")
                print(f"   Rationale: {alt.rationale}")
        else:
            print("\n[RECOMMENDED ALTERNATIVES]")
            print("No alternatives recommended")
        
        print("\n" + "=" * 80)
        print("FULL JSON RESPONSE")
        print("=" * 80)
        print(json.dumps(result.model_dump(), indent=2))
        
        return result
        
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def test_all_diagnostic_samples():
    """Test all diagnostic test samples"""
    print("\n" + "=" * 80)
    print("TESTING ALL DIAGNOSTIC TEST SAMPLES")
    print("=" * 80)
    
    results = []
    for i in range(len(TEST_SAMPLES)):
        print(f"\n\nTesting Sample {i + 1}/{len(TEST_SAMPLES)}")
        result = await test_diagnostic_validation(i)
        results.append(result)
        
        if i < len(TEST_SAMPLES) - 1:
            print("\n" + "-" * 80)
            print("Waiting 2 seconds before next test...")
            await asyncio.sleep(2)
    
    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED")
    print("=" * 80)
    
    # Summary
    print("\nSUMMARY:")
    for i, result in enumerate(results, 1):
        if result:
            status = result.quick_summary.overall_status
            print(f"Sample {i}: {status}")
        else:
            print(f"Sample {i}: FAILED")


if __name__ == "__main__":
    import sys
    
    print("Diagnostic Test Validation Testing Utility")
    print("=" * 80)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "all":
            print("Running all diagnostic test samples...")
            asyncio.run(test_all_diagnostic_samples())
        else:
            try:
                sample_idx = int(sys.argv[1])
                if 0 <= sample_idx < len(TEST_SAMPLES):
                    asyncio.run(test_diagnostic_validation(sample_idx))
                else:
                    print(f"Invalid sample index. Please use 0-{len(TEST_SAMPLES)-1}")
            except ValueError:
                print("Invalid argument. Use 'all' or a sample index (0-2)")
    else:
        print("Usage:")
        print("  python tests_validation_test.py [sample_index|all]")
        print("\nExamples:")
        print("  python tests_validation_test.py 0     # Test first sample")
        print("  python tests_validation_test.py all   # Test all samples")
        print("\nRunning first sample by default...")
        asyncio.run(test_diagnostic_validation(0))