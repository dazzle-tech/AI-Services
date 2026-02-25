import asyncio
import json
from services.medication_tests_validation_service import MedicationValidationService
from models.schemas import MedicationValidationRequest
from services.sample_clinical_data import MEDICATION_SAMPLES


async def test_medication_validation(sample_index: int = 0):
    """
    Test medication validation service with sample data
    
    Args:
        sample_index: Index of the sample to test (0-2)
    """
    print("=" * 80)
    print("MEDICATION VALIDATION TEST")
    print("=" * 80)
    
    try:
        # Initialize service
        print("\n[1] Initializing Medication Validation Service...")
        service = MedicationValidationService()
        print("✓ Service initialized successfully")
        
        # Load sample data
        print(f"\n[2] Loading sample data (Sample {sample_index + 1})...")
        sample_data = MEDICATION_SAMPLES[sample_index]
        print(f"✓ Sample data loaded: Patient MRN {sample_data['patient']['mrn']}")
        
        # Create request
        print("\n[3] Creating validation request...")
        request = MedicationValidationRequest(**sample_data)
        print(f"✓ Request created for patient: {request.patient.fullName}")
        print(f"  - Age: {request.encounter.patientAge}")
        print(f"  - Diagnosis: {request.encounter.diagnosis}")
        print(f"  - Number of medications: {len(request.medications)}")
        
        # Display medications being validated
        print("\n[4] Medications to validate:")
        for i, med in enumerate(request.medications, 1):
            print(f"  {i}. {med[:100]}...")
        
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
                print(f"   Alternative: {alt.alternative}")
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


async def test_all_medication_samples():
    """Test all medication samples"""
    print("\n" + "=" * 80)
    print("TESTING ALL MEDICATION SAMPLES")
    print("=" * 80)
    
    results = []
    for i in range(len(MEDICATION_SAMPLES)):
        print(f"\n\nTesting Sample {i + 1}/{len(MEDICATION_SAMPLES)}")
        result = await test_medication_validation(i)
        results.append(result)
        
        if i < len(MEDICATION_SAMPLES) - 1:
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
    
    print("Medication Validation Testing Utility")
    print("=" * 80)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "all":
            print("Running all medication samples...")
            asyncio.run(test_all_medication_samples())
        else:
            try:
                sample_idx = int(sys.argv[1])
                if 0 <= sample_idx < len(MEDICATION_SAMPLES):
                    asyncio.run(test_medication_validation(sample_idx))
                else:
                    print(f"Invalid sample index. Please use 0-{len(MEDICATION_SAMPLES)-1}")
            except ValueError:
                print("Invalid argument. Use 'all' or a sample index (0-2)")
    else:
        print("Usage:")
        print("  python medication_validation_test.py [sample_index|all]")
        print("\nExamples:")
        print("  python medication_validation_test.py 0     # Test first sample")
        print("  python medication_validation_test.py all   # Test all samples")
        print("\nRunning first sample by default...")
        asyncio.run(test_medication_validation(0))