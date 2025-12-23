"""Run a quick test case."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.services.discharge_qa.service import DischargeQAService

def run_test_case(test_file="quick_test_case.json"):
    """Run a test case from JSON file."""
    
    # Load test case
    test_path = Path(__file__).parent / test_file
    if not test_path.exists():
        print(f"Test file not found: {test_file}")
        return
    
    with open(test_path, "r", encoding="utf-8") as f:
        test_case = json.load(f)
    
    print("=" * 60)
    print(f"Running Test Case: {test_case.get('test_case_name', 'Unknown')}")
    print("=" * 60)
    print(f"Description: {test_case.get('description', 'N/A')}\n")
    
    # Initialize service
    print("Initializing QA service...")
    service = DischargeQAService()
    
    # Load quality rules
    rules_dir = Path(__file__).parent / "docs" / "quality_rules"
    quality_rules = None
    try:
        quality_rules = {
            "completeness": json.load(open(rules_dir / "completeness.json")),
            "consistency": json.load(open(rules_dir / "consistency.json")),
            "safety": json.load(open(rules_dir / "safety.json")),
            "structure": json.load(open(rules_dir / "structure.json"))
        }
        print("[OK] Quality rules loaded")
    except Exception as e:
        print(f"[WARNING] Could not load quality rules: {e}")
    
    # Run QA
    print("\nRunning QA analysis...")
    print("(This may take 30-60 seconds...)\n")
    
    try:
        result = service.perform_qa(
            discharge_report=test_case["discharge_report"],
            patient_record=test_case["patient_record"],
            onsite_docs=test_case.get("onsite_docs", []),
            report_template=test_case.get("report_template"),
            quality_rules=quality_rules
        )
        
        # Display results
        print("=" * 60)
        print("RESULTS")
        print("=" * 60)
        
        print(f"\n[SCORE] Overall Score: {result['overall_score']}/100")
        
        # Check expected results if provided
        if "expected_results" in test_case:
            expected = test_case["expected_results"]
            min_score = expected.get("min_score", 0)
            max_errors = expected.get("max_errors", 100)
            
            print(f"\n[EXPECTED] Min Score: {min_score}, Max Errors: {max_errors}")
            
            if result["overall_score"] >= min_score:
                print("[PASS] Score meets minimum requirement")
            else:
                print(f"[FAIL] Score {result['overall_score']} is below minimum {min_score}")
            
            if len(result["errors"]) <= max_errors:
                print(f"[PASS] Error count {len(result['errors'])} is within limit")
            else:
                print(f"[FAIL] Error count {len(result['errors'])} exceeds limit {max_errors}")
        
        print(f"\n[SUMMARY]\n{result['summary']}")
        
        print(f"\n[ERRORS] {len(result['errors'])}")
        for i, error in enumerate(result['errors'][:5], 1):
            print(f"  {i}. [{error.get('severity', 'unknown').upper()}] {error.get('category', 'unknown')}")
            print(f"     {error.get('issue', 'N/A')[:70]}...")
        
        print(f"\n[MISSING] {len(result['missing_items'])}")
        for i, item in enumerate(result['missing_items'][:5], 1):
            print(f"  {i}. {item.get('section', 'N/A')}.{item.get('field', 'N/A')}")
        
        print(f"\n[INCONSISTENCIES] {len(result['inconsistencies'])}")
        for i, inc in enumerate(result['inconsistencies'][:5], 1):
            print(f"  {i}. [{inc.get('severity', 'unknown').upper()}] {inc.get('section', 'N/A')}")
        
        print(f"\n[CORRECTIONS] {len(result['recommended_corrections'])}")
        for i, fix in enumerate(result['recommended_corrections'][:5], 1):
            print(f"  {i}. [{fix.get('action', 'unknown')}] {fix.get('section', 'N/A')}")
        
        # Save results
        output_file = Path(__file__).parent / "test_case_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n[SAVED] Full results saved to: {output_file}")
        
        print("\n" + "=" * 60)
        print("Test completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_file = sys.argv[1] if len(sys.argv) > 1 else "quick_test_case.json"
    run_test_case(test_file)

