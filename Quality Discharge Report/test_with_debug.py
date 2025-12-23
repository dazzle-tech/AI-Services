"""Test script with debug logging enabled."""

import logging
import json
import sys
from pathlib import Path

# Configure logging to show DEBUG level in terminal
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Terminal output
        logging.FileHandler('debug.log', mode='w')  # File output
    ],
    force=True  # Override any existing configuration
)

# Also configure root logger to ensure all logs show
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
for handler in root_logger.handlers:
    handler.setLevel(logging.DEBUG)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.services.discharge_qa.service import DischargeQAService

def main():
    print("=" * 60)
    print("Testing with Debug Logging")
    print("=" * 60)
    print("\nDebug logs will be written to:")
    print("1. Console (stdout)")
    print("2. debug.log file")
    print("\n" + "=" * 60 + "\n")
    
    # Load test data
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures"
    
    with open(fixtures_dir / "discharge_report_text.txt", "r", encoding="utf-8") as f:
        discharge_report = f.read()
    
    with open(fixtures_dir / "patient_record.json", "r", encoding="utf-8") as f:
        patient_record = json.load(f)
    
    with open(fixtures_dir / "onsite_docs.json", "r", encoding="utf-8") as f:
        onsite_docs = json.load(f)
    
    # Load quality rules
    rules_dir = Path(__file__).parent / "docs" / "quality_rules"
    quality_rules = {
        "completeness": json.load(open(rules_dir / "completeness.json")),
        "consistency": json.load(open(rules_dir / "consistency.json")),
        "safety": json.load(open(rules_dir / "safety.json")),
        "structure": json.load(open(rules_dir / "structure.json"))
    }
    
    # Run QA
    print("Running QA analysis with debug logging...\n")
    service = DischargeQAService()
    
    result = service.perform_qa(
        discharge_report=discharge_report,
        patient_record=patient_record,
        onsite_docs=onsite_docs,
        report_template=None,
        quality_rules=quality_rules
    )
    
    # Check medications in result
    print("\n" + "=" * 60)
    print("FINAL RESULT - Medications Check")
    print("=" * 60)
    
    if "parsed_report" in result and "content" in result["parsed_report"]:
        content = result["parsed_report"]["content"]
        if "medications" in content and "discharge_medications" in content["medications"]:
            meds = content["medications"]["discharge_medications"]
            print(f"\nFound {len(meds)} discharge medications in final result:")
            for i, med in enumerate(meds[:3], 1):
                print(f"\n  Medication {i}:")
                if isinstance(med, dict):
                    print(f"    Name: {med.get('name')}")
                    print(f"    Dose: {med.get('dose')}")
                    print(f"    Route: {med.get('route')}")
                    print(f"    Frequency: {med.get('frequency')}")
                    if med.get("dose") or med.get("frequency"):
                        print(f"    ✓ Properly parsed!")
                    else:
                        print(f"    ✗ NOT properly parsed!")
                else:
                    print(f"    {med}")
        else:
            print("\nNo medications found in final result")
    else:
        print("\nNo parsed_report.content found in result")
    
    print("\n" + "=" * 60)
    print("Check debug.log for detailed logs")
    print("=" * 60)

if __name__ == "__main__":
    main()

