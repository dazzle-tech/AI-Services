"""Simple test script for the Discharge QA Service."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.services.discharge_qa.service import DischargeQAService

def main():
    print("=" * 60)
    print("Discharge QA Service - Test Script")
    print("=" * 60)
    
    # Load test data
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures"
    
    print("\n1. Loading test data...")
    try:
        with open(fixtures_dir / "discharge_report_text.txt", "r", encoding="utf-8") as f:
            discharge_report = f.read()
        print("   [OK] Discharge report loaded")
        
        with open(fixtures_dir / "patient_record.json", "r", encoding="utf-8") as f:
            patient_record = json.load(f)
        print("   [OK] Patient record loaded")
        
        with open(fixtures_dir / "onsite_docs.json", "r", encoding="utf-8") as f:
            onsite_docs = json.load(f)
        print("   [OK] Onsite documents loaded")
        
        with open(fixtures_dir / "report_template.json", "r", encoding="utf-8") as f:
            report_template = json.load(f)
        print("   [OK] Report template loaded")
        
    except Exception as e:
        print(f"   [ERROR] Error loading test data: {e}")
        return
    
    # Load quality rules
    print("\n2. Loading quality rules...")
    try:
        rules_dir = Path(__file__).parent / "docs" / "quality_rules"
        quality_rules = {
            "completeness": json.load(open(rules_dir / "completeness.json")),
            "consistency": json.load(open(rules_dir / "consistency.json")),
            "safety": json.load(open(rules_dir / "safety.json")),
            "structure": json.load(open(rules_dir / "structure.json"))
        }
        print("   [OK] Quality rules loaded")
    except Exception as e:
        print(f"   [ERROR] Error loading quality rules: {e}")
        quality_rules = None
    
    # Initialize service
    print("\n3. Initializing QA service...")
    try:
        service = DischargeQAService()
        print("   [OK] Service initialized")
    except Exception as e:
        print(f"   [ERROR] Error initializing service: {e}")
        print(f"   Make sure your .env file has OPENAI_API_KEY set")
        return
    
    # Perform QA
    print("\n4. Running QA analysis...")
    print("   (This may take 30-60 seconds...)")
    try:
        result = service.perform_qa(
            discharge_report=discharge_report,
            patient_record=patient_record,
            onsite_docs=onsite_docs,
            report_template=report_template,
            quality_rules=quality_rules
        )
        print("   [OK] QA analysis completed")
    except Exception as e:
        print(f"   [ERROR] Error during QA analysis: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Display results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    print(f"\n[SCORE] Overall Score: {result['overall_score']}/100")
    print(f"\n[SUMMARY]\n{result['summary']}")
    
    print(f"\n[ERRORS] {len(result['errors'])}")
    if result['errors']:
        for i, error in enumerate(result['errors'][:5], 1):
            print(f"   {i}. [{error.get('severity', 'unknown').upper()}] {error.get('category', 'unknown')}")
            print(f"      {error.get('issue', 'N/A')[:80]}...")
    
    print(f"\n[MISSING] Missing Items: {len(result['missing_items'])}")
    if result['missing_items']:
        for i, item in enumerate(result['missing_items'][:5], 1):
            print(f"   {i}. {item.get('section', 'N/A')}.{item.get('field', 'N/A')}")
    
    print(f"\n[INCONSISTENCIES] {len(result['inconsistencies'])}")
    if result['inconsistencies']:
        for i, inc in enumerate(result['inconsistencies'][:5], 1):
            print(f"   {i}. [{inc.get('severity', 'unknown').upper()}] {inc.get('section', 'N/A')}")
            print(f"      Report: {str(inc.get('report_value', 'N/A'))[:50]}")
            print(f"      Source: {str(inc.get('source_value', 'N/A'))[:50]}")
    
    print(f"\n[CORRECTIONS] Recommended Corrections: {len(result['recommended_corrections'])}")
    if result['recommended_corrections']:
        for i, fix in enumerate(result['recommended_corrections'][:5], 1):
            print(f"   {i}. [{fix.get('action', 'unknown')}] {fix.get('section', 'N/A')}")
    
    # Save full result
    output_file = Path(__file__).parent / "qa_output.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] Full results saved to: {output_file}")
    
    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()

