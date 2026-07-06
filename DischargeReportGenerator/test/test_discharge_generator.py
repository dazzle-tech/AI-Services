"""Test script for Discharge Report Generation System.

Run this file directly to exercise the CLI workflow, or run pytest to execute
the regression tests below.
"""

import asyncio
import os
from datetime import datetime

import pytest

from models.schemas import ClinicalDocumentation, DischargeReportSection, PatientRecord, ReportTemplate
from services.discharge_report_service import (
    DischargeReportGenerator,
    discharge_report_generator,
)
from services.discharge_sample_data import (
    get_sample_discharge_patient,
    get_sample_template,
)


def print_separator(title=""):
    """Print a visual separator."""
    if title:
        print(f"\n{'=' * 80}")
        print(f"  {title}")
        print(f"{'=' * 80}\n")
    else:
        print(f"{'=' * 80}\n")


def print_report_section(section, index):
    """Pretty print a report section."""
    print(f"Section {index}: {section.section_name}")
    print(f"{'─' * 80}")
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
    print("\nReport Statistics:")
    print(f"   Total Sections: {len(response.report_sections)}")
    print(f"   Total Length: {len(response.full_report_text)} characters")
    print(f"   Requires Review: {'Yes' if response.requires_physician_review else 'No'}")

    if response.template_used:
        print(f"\nTemplate Used: {response.template_used.get('template_name')}")


async def test_quick_generate(patient_id="DISCH001", template_name="standard"):
    """Test quick generation with sample data."""

    print_separator(f"Testing Quick Generate: {patient_id} with {template_name} template")

    sample_data = get_sample_discharge_patient(patient_id)
    if not sample_data:
        print(f"Sample patient {patient_id} not found!")
        return None

    patient = sample_data["patient"]
    print("Patient Information:")
    print(f"   ID: {patient.patient_id}")
    print(f"   Age: {patient.age}, Gender: {patient.gender}")
    print(f"   Primary Diagnosis: {patient.primary_diagnosis}")
    print(f"   Admission: {patient.admission_date}")
    print(f"   Discharge: {patient.discharge_date}")
    print()

    template = get_sample_template(template_name)

    if not discharge_report_generator.initialized:
        print("Initializing discharge report generator...")
        discharge_report_generator.initialize()

    print("Generating discharge report with AI...")
    print("   (This may take 20-40 seconds...)")
    print()

    start_time = datetime.now()

    try:
        result = await discharge_report_generator.generate_discharge_report(
            patient_record=sample_data["patient"],
            clinical_documentation=sample_data["documentation"],
            report_template=template,
            generation_mode="template",
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"Report generated in {duration:.1f} seconds")

    except Exception as e:
        print(f"\nError during report generation: {e}")
        import traceback

        traceback.print_exc()
        return None

    print_separator("Generated Report Summary")
    print_report_summary(result)

    if result.report_sections:
        print_separator("Report Sections")
        for i, section in enumerate(result.report_sections, 1):
            print_report_section(section, i)

    print_separator("Full Report Text")
    print(result.full_report_text)

    print_separator()
    print("IMPORTANT DISCLAIMER:")
    print(result.disclaimer)

    return result


async def test_freeform_generate(patient_id="DISCH001"):
    """Test freeform generation without template."""

    print_separator(f"Testing Freeform Generate: {patient_id}")

    sample_data = get_sample_discharge_patient(patient_id)
    if not sample_data:
        print(f"Sample patient {patient_id} not found!")
        return None

    print("Generating discharge report in FREEFORM mode...")
    print("   AI will create comprehensive report with standard sections")
    print("   (This may take 25-45 seconds...)")
    print()

    if not discharge_report_generator.initialized:
        discharge_report_generator.initialize()

    start_time = datetime.now()

    try:
        result = await discharge_report_generator.generate_discharge_report(
            patient_record=sample_data["patient"],
            clinical_documentation=sample_data["documentation"],
            report_template=None,
            generation_mode="freeform",
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"Freeform report generated in {duration:.1f} seconds")

    except Exception as e:
        print(f"\nError during report generation: {e}")
        import traceback

        traceback.print_exc()
        return None

    print_separator("Generated Report Summary")
    print_report_summary(result)

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

    if not discharge_report_generator.initialized:
        discharge_report_generator.initialize()

    sample_data = get_sample_discharge_patient("DISCH001")

    results = {}
    for template_name in ["standard", "cardiac"]:
        print(f"Generating with {template_name} template...")

        template = get_sample_template(template_name)

        start_time = datetime.now()

        result = await discharge_report_generator.generate_discharge_report(
            patient_record=sample_data["patient"],
            clinical_documentation=sample_data["documentation"],
            report_template=template,
            generation_mode="template",
        )

        duration = (datetime.now() - start_time).total_seconds()
        results[template_name] = {"result": result, "duration": duration}

        print(f"   Complete in {duration:.1f}s - {len(result.report_sections)} sections\n")

    print_separator("Comparison Results")
    print(f"{'Template':<15} {'Sections':<10} {'Confidence':<12} {'Length':<10} {'Time (s)':<10}")
    print("-" * 60)

    for template_name, data in results.items():
        result = data["result"]
        print(
            f"{template_name:<15} {len(result.report_sections):<10} "
            f"{result.confidence_score:<12.2%} {len(result.full_report_text):<10} {data['duration']:<10.1f}"
        )

    print()
    print("Section Differences:")
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


test_quick_generate.__test__ = False
test_freeform_generate.__test__ = False
compare_templates.__test__ = False


@pytest.mark.asyncio
async def test_prompt_uses_template_section_names():
    """The prompt example should mirror the actual template sections."""

    generator = DischargeReportGenerator()
    sample = get_sample_discharge_patient("DISCH001")
    patient = sample["patient"]
    docs = sample["documentation"]
    template = ReportTemplate(
        template_name="Non-Chief Complaint Template",
        sections=["Admission Summary", "Hospital Events"],
        required_fields=[],
        format_type="custom",
    )

    prompt = generator._build_template_prompt(patient, docs, template)

    assert '"section_name": "Chief Complaint"' not in prompt
    assert "Admission Summary" in prompt
    assert "Hospital Events" in prompt


@pytest.mark.asyncio
async def test_allergy_string_is_preserved_in_full_report_text(monkeypatch):
    """Known allergies should appear in the final report text when present."""

    generator = DischargeReportGenerator()
    generator.initialized = True

    async def fake_call(*args, **kwargs):
        return [
            DischargeReportSection(
                section_name="Discharge Diagnosis",
                content="Acute coronary syndrome.",
                confidence=0.95,
                sources=["admission_notes", "progress_notes"],
            ),
            DischargeReportSection(
                section_name="Hospital Course",
                content="Patient stabilized after PCI.",
                confidence=0.90,
                sources=["progress_notes", "procedures"],
            ),
        ]

    monkeypatch.setattr(generator, "_call_openai_for_report", fake_call)

    sample = get_sample_discharge_patient("DISCH001")
    result = await generator.generate_discharge_report(
        patient_record=sample["patient"],
        clinical_documentation=sample["documentation"],
        report_template=ReportTemplate(
            template_name="Allergy Check",
            sections=["Discharge Diagnosis", "Hospital Course"],
            required_fields=[],
            format_type="standard",
        ),
        generation_mode="template",
    )

    assert "Penicillin" in result.full_report_text
    assert "Known allergies" in result.full_report_text


@pytest.mark.asyncio
async def test_untraceable_tte_tee_term_is_flagged(monkeypatch):
    """A generated TEE term should be flagged when the sources only support TTE."""

    generator = DischargeReportGenerator()
    generator.initialized = True

    async def fake_call(*args, **kwargs):
        return [
            DischargeReportSection(
                section_name="Echocardiographic Findings",
                content="TEE showed LVEF 45% with inferolateral hypokinesis.",
                confidence=0.95,
                sources=["progress_notes", "procedures"],
            )
        ]

    monkeypatch.setattr(generator, "_call_openai_for_report", fake_call)

    sample = get_sample_discharge_patient("DISCH001")
    result = await generator.generate_discharge_report(
        patient_record=sample["patient"],
        clinical_documentation=sample["documentation"],
        report_template=get_sample_template("standard"),
        generation_mode="template",
    )

    section = result.report_sections[0]
    assert "source says tte, generated text says tee" in section.content.lower()
    assert section.confidence < 0.95
    assert "TEE" in section.content
    assert "TTE" in sample["documentation"].progress_notes[1]


@pytest.mark.asyncio
async def test_stemii_and_st_from_primary_diagnosis_do_not_trigger_warning():
    """STEMI and ST should remain verified when they are in the primary diagnosis."""

    generator = DischargeReportGenerator()
    generator.initialized = True

    patient = PatientRecord(
        patient_id="DISCH999",
        age=58,
        gender="M",
        admission_date="2025-12-18",
        discharge_date="2025-12-23",
        primary_diagnosis="Acute ST-Elevation Myocardial Infarction (STEMI)",
        secondary_diagnoses=["Hypertension"],
        allergies=[],
        medications_on_admission=[],
    )
    docs = ClinicalDocumentation(
        progress_notes=["Patient with STEMI underwent PCI."],
        admission_notes="ST-elevation myocardial infarction noted on arrival.",
    )

    section = DischargeReportSection(
        section_name="Hospital Course",
        content="ST-elevation myocardial infarction (STEMI) was treated with PCI.",
        confidence=0.92,
        sources=["primary_diagnosis", "progress_notes"],
    )

    checked = generator._flag_untraceable_clinical_terms(section, patient, docs)

    assert "Reviewer warning" not in checked.content
    assert checked.confidence == section.confidence


def main():
    """Main test menu for manual CLI execution."""

    from dotenv import load_dotenv

    load_dotenv()

    print("\n" + "=" * 80)
    print("  DISCHARGE REPORT GENERATION - TEST SUITE")
    print("=" * 80)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\nOPENAI_API_KEY is not set.")
        print("Add it to .env if you want to run the interactive CLI.")
        return

    print(f"\nOpenAI API Key loaded: {api_key[:15]}...{api_key[-4:]}")

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
        print("\nInvalid choice!")
        return

    print("\n" + "=" * 80)
    cont = input("Run another test? (y/n): ").strip().lower()
    if cont == "y":
        main()


if __name__ == "__main__":
    main()
