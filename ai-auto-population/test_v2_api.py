"""Test case for AI Auto-Population Service V2 API."""
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.models.schemas_v2 import AutoPopulationRequestV2, User, Languages, Inputs, OnsiteData, DocumentReference, RequestedOutputs
from app.services.auto_population_service_v2 import AutoPopulationServiceV2
from app.core.constants import UserRole, SupportedLanguage


def test_v2_api_summary_and_vitals_only():
    """Test V2 API with summary and vitals only (no structured fields)."""
    print("=" * 70)
    print("Testing AI Auto-Population Service V2 API")
    print("Request: Summary + Vitals Only")
    print("=" * 70)
    
    # Create test request
    request = AutoPopulationRequestV2(
        request_id="test_v2_001",
        task_type="auto_population",
        user=User(
            user_id="doctor_123",
            role=UserRole.DOCTOR,
            department="cardiology"
        ),
        languages=Languages(
            input=SupportedLanguage.EN,
            output=SupportedLanguage.EN
        ),
        inputs=Inputs(
            user_text=(
                "Patient is a 65-year-old male presenting with acute chest pain "
                "that started 2 hours ago. Blood pressure is 150/90, heart rate 95 bpm. "
                "Patient has history of hypertension and is currently taking Lisinopril 10mg daily. "
                "No known allergies. Assessment: Possible acute coronary syndrome. "
                "Plan: EKG, cardiac enzymes, aspirin 325mg."
            ),
            onsite=OnsiteData(
                patient_record_id="pr_456",
                is_deidentified=True,
                documents=[
                    DocumentReference(
                        doc_id="doc_1",
                        doc_type="patient_history"
                    )
                ],
                patient_data={
                    "medications": [
                        {
                            "name": "Lisinopril",
                            "dosage": "10mg",
                            "frequency": "daily"
                        }
                    ],
                    "allergies": [],
                    "vitals": {
                        "bp": "140/85",
                        "hr": "92"
                    },
                    "past_medical_history": ["hypertension"]
                }
            )
        ),
        requested_outputs=RequestedOutputs(
            include_summary=True,
            include_structured_fields=False,  # Only summary and vitals
            include_vitals=True,
            include_quality_indicators=False,  # Don't include quality section
            include_trace=False  # Don't include trace section
        )
    )
    
    print(f"\n[OK] Test request created: {request.request_id}")
    print(f"  User: {request.user.user_id} ({request.user.role.value})")
    print(f"  Department: {request.user.department}")
    print(f"  Requested outputs:")
    print(f"    - Summary: {request.requested_outputs.include_summary}")
    print(f"    - Structured Fields: {request.requested_outputs.include_structured_fields}")
    print(f"    - Vitals: {request.requested_outputs.include_vitals}")
    
    # Initialize service
    print("\n" + "-" * 70)
    print("Initializing Auto-Population Service V2...")
    try:
        service = AutoPopulationServiceV2()
        print("[OK] Service initialized successfully")
    except Exception as e:
        print(f"[FAIL] Failed to initialize service: {e}")
        return False
    
    # Process request
    print("\n" + "-" * 70)
    print("Processing request...")
    print("(This may take 10-30 seconds depending on API response time)")
    
    try:
        response = service.process_request(request)
        print("[OK] Request processed successfully")
    except Exception as e:
        print(f"[FAIL] Failed to process request: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Validate response
    print("\n" + "-" * 70)
    print("Validating response...")
    
    # Check basic structure
    assert response.request_id == request.request_id, "Request ID mismatch"
    assert response.task_type.value == "auto_population", "Task type mismatch"
    print("[OK] Basic response structure valid")
    
    # Check outputs structure
    assert response.outputs is not None, "Outputs missing"
    assert response.outputs.summary is not None, "Summary should be present"
    assert response.outputs.structured_fields is None, "Structured fields should be None"
    assert response.outputs.vitals is not None, "Vitals should be present"
    print("[OK] Outputs structure valid (summary + vitals only)")
    
    # Check quality section (optional)
    if request.requested_outputs.include_quality_indicators:
        assert response.quality is not None, "Quality section missing"
        print("[OK] Quality section present")
    else:
        assert response.quality is None, "Quality section should be None when not requested"
        print("[OK] Quality section excluded (as requested)")
    
    # Check trace section (optional)
    if request.requested_outputs.include_trace:
        assert response.trace is not None, "Trace section missing"
        print("[OK] Trace section present")
    else:
        assert response.trace is None, "Trace section should be None when not requested"
        print("[OK] Trace section excluded (as requested)")
    
    # Check metadata
    assert response.metadata is not None, "Metadata missing"
    assert response.metadata.schema_version is not None, "Schema version missing"
    print("[OK] Metadata present")
    
    # Display results
    print("\n" + "=" * 70)
    print("RESPONSE SUMMARY")
    print("=" * 70)
    
    print(f"\nRequest ID: {response.request_id}")
    print(f"Task Type: {response.task_type.value}")
    print(f"Schema Version: {response.metadata.schema_version}")
    
    print("\n--- Outputs ---")
    print(f"Summary: {response.outputs.summary[:100]}..." if len(response.outputs.summary) > 100 else f"Summary: {response.outputs.summary}")
    print(f"Structured Fields: {response.outputs.structured_fields}")
    print(f"Vitals: {response.outputs.vitals}")
    
    if response.quality:
        print(f"\n--- Quality Indicators ---")
        print(f"Uncertainty Flags: {len(response.quality.uncertainty_flags)}")
        for flag in response.quality.uncertainty_flags[:3]:  # Show first 3
            print(f"  - {flag.field_name}: {flag.reason[:50]}...")
        if len(response.quality.uncertainty_flags) > 3:
            print(f"  ... and {len(response.quality.uncertainty_flags) - 3} more")
        
        print(f"Contradictions: {len(response.quality.contradictions)}")
        for contradiction in response.quality.contradictions:
            print(f"  - {contradiction.field_name}: {contradiction.severity} severity")
        
        print(f"Warnings: {len(response.quality.warnings)}")
        for warning in response.quality.warnings:
            print(f"  - [{warning.level}] {warning.message}")
    else:
        print(f"\n--- Quality Indicators ---")
        print("  (Excluded from response)")
    
    if response.trace:
        print(f"\n--- Trace ---")
        print(f"Source Trace Entries: {len(response.trace.source_trace)}")
    else:
        print(f"\n--- Trace ---")
        print("  (Excluded from response)")
    
    print(f"\n--- Metadata ---")
    print(f"Model Used: {response.metadata.model_used}")
    print(f"User Role: {response.metadata.user_role}")
    print(f"Department: {response.metadata.department}")
    print(f"Processing Timestamp: {response.metadata.processing_timestamp}")
    
    print("\n" + "=" * 70)
    print("[SUCCESS] TEST PASSED")
    print("=" * 70)
    print("\nResponse structure matches V2 API contract:")
    print("  [OK] Summary included")
    print("  [OK] Structured fields excluded (null)")
    print("  [OK] Vitals included")
    if request.requested_outputs.include_quality_indicators:
        print("  [OK] Quality indicators included")
    else:
        print("  [OK] Quality indicators excluded (as requested)")
    if request.requested_outputs.include_trace:
        print("  [OK] Trace information included")
    else:
        print("  [OK] Trace information excluded (as requested)")
    print("  [OK] Metadata complete")
    
    return True


if __name__ == "__main__":
    try:
        success = test_v2_api_summary_and_vitals_only()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[WARNING] Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[FAIL] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

