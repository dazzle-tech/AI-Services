"""
Test script for Discharge Report Generation System
Run this to test the discharge report generator without starting the server.
"""

import asyncio
import json
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

print("✅ Environment variables loaded from .env file")

# Check for OpenAI API key
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("⚠️  ERROR: OPENAI_API_KEY environment variable not set!")
    print("   Please add your OpenAI API key to .env file:")
    print("   OPENAI_API_KEY=sk-your-key-here")
    print()
    exit(1)

print(f"✅ OpenAI API Key loaded: {api_key[:15]}...{api_key[-4:]}")
print()

# Import services
from services.discharge_report_service import discharge_report_generator
from services.discharge_sample_data import (
    get_sample_discharge_patient,
    get_sample_template
)


def print_separator(title=""):
    """Print a visual separator."""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}\n")
    else:
        print(f"{'='*80}\n")


def print_report_section(section, index):
    """Pretty print a report section."""
    print(f"📄 Section {index}: {section.section_name}")
    print(f"{'─'*80}")
    print(f"Confidence: {section.confidence:.2%}")
    if section.sources:
        print(f"Sources: {', '.join(section.sources)}")
    print()
    print(section.content)
    print()


def print_report_summary(response):
    """Print summary of generated report."""
    print(f"Patient ID: {response.patient_id}")
    print(f"Generated: {response.generation_timestamp}")
    print(f"Mode: {response.generation_mode}")
    print(f"Overall Confidence: {response.confidence_score:.2%}")
    print(f"\n📊 Report Statistics:")
    print(f"   Total Sections: {len(response.report_sections)}")
    print(f"   Total Length: {len(response.full_report_text)} characters")
    print(f"   Requires Review: {'Yes' if response.requires_physician_review else 'No'}")
    
    if response.template_used:
        print(f"\n📋 Template Used: {response.template_used.get('template_name')}")


async def test_quick_generate(patient_id="DISCH001", template_name="standard"):
    """Test quick generation with sample data."""
    
    print_separator(f"Testing Quick Generate: {patient_id} with {template_name} template")
    
    # Get sample data
    sample_data = get_sample_discharge_patient(patient_id)
    
    if not sample_data:
        print(f"❌ Sample patient {patient_id} not found!")
        return None
    
    # Show patient info
    patient = sample_data["patient"]
    print(f"👤 Patient Information:")
    print(f"   ID: {patient.patient_id}")
    print(f"   Age: {patient.age}, Gender: {patient.gender}")
    print(f"   Primary Diagnosis: {patient.primary_diagnosis}")
    print(f"   Admission: {patient.admission_date}")
    print(f"   Discharge: {patient.discharge_date}")
    print()
    
    # Get template
    template = get_sample_template(template_name)
    
    # Initialize generator
    if not discharge_report_generator.initialized:
        print("🔧 Initializing discharge report generator...")
        discharge_report_generator.initialize()
    
    # Generate report
    print("🤖 Generating discharge report with AI...")
    print("   (This may take 20-40 seconds...)")
    print()
    
    start_time = datetime.now()
    
    try:
        result = await discharge_report_generator.generate_discharge_report(
            patient_record=sample_data["patient"],
            clinical_documentation=sample_data["documentation"],
            report_template=template,
            generation_mode="template"
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"✅ Report generated in {duration:.1f} seconds")
        
    except Exception as e:
        print(f"\n❌ Error during report generation: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    print_separator("Generated Report Summary")
    
    # Print summary
    print_report_summary(result)
    
    # Print sections
    if result.report_sections:
        print_separator("Report Sections")
        for i, section in enumerate(result.report_sections, 1):
            print_report_section(section, i)
    
    # Print full report
    print_separator("Full Report Text")
    print(result.full_report_text)
    
    # Print disclaimer
    print_separator()
    print("⚠️  IMPORTANT DISCLAIMER:")
    print(result.disclaimer)
    
    return result


async def test_freeform_generate(patient_id="DISCH001"):
    """Test freeform generation without template."""
    
    print_separator(f"Testing Freeform Generate: {patient_id}")
    
    # Get sample data
    sample_data = get_sample_discharge_patient(patient_id)
    
    if not sample_data:
        print(f"❌ Sample patient {patient_id} not found!")
        return None
    
    print("🤖 Generating discharge report in FREEFORM mode...")
    print("   AI will create comprehensive report with standard sections")
    print("   (This may take 25-45 seconds...)")
    print()
    
    # Initialize generator
    if not discharge_report_generator.initialized:
        discharge_report_generator.initialize()
    
    start_time = datetime.now()
    
    try:
        result = await discharge_report_generator.generate_discharge_report(
            patient_record=sample_data["patient"],
            clinical_documentation=sample_data["documentation"],
            report_template=None,
            generation_mode="freeform"
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"✅ Freeform report generated in {duration:.1f} seconds")
        
    except Exception as e:
        print(f"\n❌ Error during report generation: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    print_separator("Generated Report Summary")
    
    print_report_summary(result)
    
    # Print sections
    if result.report_sections:
        print_separator("Report Sections")
        for i, section in enumerate(result.report_sections, 1):
            print_report_section(section, i)
    
    return result


async def compare_templates():
    """Compare standard vs cardiac templates."""
    
    print_separator("Comparing Templates: Standard vs Cardiac")
    
    print("Generating reports with both templates for comparison...")
    print()
    
    # Initialize generator
    if not discharge_report_generator.initialized:
        discharge_report_generator.initialize()
    
    sample_data = get_sample_discharge_patient("DISCH001")
    
    results = {}
    
    for template_name in ["standard", "cardiac"]:
        print(f"📋 Generating with {template_name} template...")
        
        template = get_sample_template(template_name)
        
        start_time = datetime.now()
        
        result = await discharge_report_generator.generate_discharge_report(
            patient_record=sample_data["patient"],
            clinical_documentation=sample_data["documentation"],
            report_template=template,
            generation_mode="template"
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        results[template_name] = {
            "result": result,
            "duration": duration
        }
        
        print(f"   ✅ Complete in {duration:.1f}s - {len(result.report_sections)} sections\n")
    
    # Print comparison
    print_separator("Comparison Results")
    
    print(f"{'Template':<15} {'Sections':<10} {'Confidence':<12} {'Length':<10} {'Time (s)':<10}")
    print("-" * 60)
    
    for template_name, data in results.items():
        result = data["result"]
        print(f"{template_name:<15} {len(result.report_sections):<10} {result.confidence_score:<12.2%} {len(result.full_report_text):<10} {data['duration']:<10.1f}")
    
    print()
    
    # Show section differences
    print("📋 Section Differences:")
    print()
    
    standard_sections = [s.section_name for s in results["standard"]["result"].report_sections]
    cardiac_sections = [s.section_name for s in results["cardiac"]["result"].report_sections]
    
    print("Standard template sections:")
    for s in standard_sections:
        print(f"   • {s}")
    
    print()
    print("Cardiac template sections:")
    for s in cardiac_sections:
        print(f"   • {s}")
    
    print()


def main():
    """Main test menu."""
    
    print("\n" + "="*80)
    print("  📝 DISCHARGE REPORT GENERATION - TEST SUITE")
    print("="*80)
    
    print("\nSelect a test option:")
    print("  1. Quick test (Standard template)")
    print("  2. Quick test (Cardiac template)")
    print("  3. Freeform generation (no template)")
    print("  4. Compare templates (Standard vs Cardiac)")
    print("  5. Exit")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        asyncio.run(test_quick_generate("DISCH001", "standard"))
    
    elif choice == "2":
        asyncio.run(test_quick_generate("DISCH001", "cardiac"))
    
    elif choice == "3":
        asyncio.run(test_freeform_generate("DISCH001"))
    
    elif choice == "4":
        asyncio.run(compare_templates())
    
    elif choice == "5":
        print("\nExiting...")
        return
    
    else:
        print("\n❌ Invalid choice!")
    
    # Ask to continue
    print("\n" + "="*80)
    cont = input("Run another test? (y/n): ").strip().lower()
    if cont == "y":
        main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()