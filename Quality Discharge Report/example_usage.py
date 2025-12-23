"""Example usage of the Discharge QA Service."""

import json
from pathlib import Path
from src.services.discharge_qa.service import DischargeQAService

# Load fixtures
fixtures_dir = Path(__file__).parent / "tests" / "fixtures"

with open(fixtures_dir / "discharge_report_text.txt", "r") as f:
    discharge_report = f.read()

with open(fixtures_dir / "patient_record.json", "r") as f:
    patient_record = json.load(f)

with open(fixtures_dir / "onsite_docs.json", "r") as f:
    onsite_docs = json.load(f)

with open(fixtures_dir / "report_template.json", "r") as f:
    report_template = json.load(f)

# Load quality rules
quality_rules = {
    "completeness": json.load(open(fixtures_dir.parent.parent / "docs" / "quality_rules" / "completeness.json")),
    "consistency": json.load(open(fixtures_dir.parent.parent / "docs" / "quality_rules" / "consistency.json")),
    "safety": json.load(open(fixtures_dir.parent.parent / "docs" / "quality_rules" / "safety.json")),
    "structure": json.load(open(fixtures_dir.parent.parent / "docs" / "quality_rules" / "structure.json"))
}

# Perform QA
print("Running Discharge QA Analysis...")
print("=" * 50)

service = DischargeQAService()

try:
    result = service.perform_qa(
        discharge_report=discharge_report,
        patient_record=patient_record,
        onsite_docs=onsite_docs,
        report_template=report_template,
        quality_rules=quality_rules
    )
    
    print(f"\nOverall Score: {result['overall_score']}/100")
    print(f"\nSummary:\n{result['summary']}")
    
    print(f"\nErrors: {len(result['errors'])}")
    for error in result['errors'][:5]:  # Show first 5
        print(f"  - [{error.get('severity', 'unknown')}] {error.get('issue', 'N/A')}")
    
    print(f"\nMissing Items: {len(result['missing_items'])}")
    for item in result['missing_items'][:5]:  # Show first 5
        print(f"  - {item.get('section', 'N/A')}.{item.get('field', 'N/A')}")
    
    print(f"\nInconsistencies: {len(result['inconsistencies'])}")
    for inc in result['inconsistencies'][:5]:  # Show first 5
        print(f"  - [{inc.get('severity', 'unknown')}] {inc.get('section', 'N/A')}")
    
    # Save full result
    output_file = Path(__file__).parent / "qa_output.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\nFull results saved to: {output_file}")
    
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()

