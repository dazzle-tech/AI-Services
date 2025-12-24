"""
Test script for OpenAI-Powered Medical Guideline Validation
Tests the AI validator with sample patients.
"""

import asyncio
import json
import os
from datetime import datetime

# ============================================
# LOAD ENVIRONMENT VARIABLES FROM .env FILE
# ============================================
from dotenv import load_dotenv
load_dotenv()

print("✅ Environment variables loaded from .env file")
# ============================================

# Check for OpenAI API key
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("⚠️  ERROR: OPENAI_API_KEY environment variable not set!")
    print("   Please set your OpenAI API key:")
    print("   1. Create a .env file in your project root")
    print("   2. Add this line: OPENAI_API_KEY=sk-your-key-here")
    print()
    exit(1)

print(f"✅ OpenAI API Key loaded: {api_key[:15]}...{api_key[-4:]}")
print()

# Import the OpenAI validator and sample data
from services.guidelines_validator_service import openai_guideline_validator
from services.sample_clinical_data import get_patient_data, list_all_patients


def print_separator(title=""):
    """Print a visual separator."""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}\n")
    else:
        print(f"{'='*80}\n")


def print_ai_note(note, index):
    """Pretty print an AI-generated medical note."""
    severity_emoji = {
        "critical": "🚨",
        "high": "⚠️",
        "urgent": "🔴",
        "moderate": "🟡",
        "low": "🔵",
        "routine": "⚪"
    }
    
    emoji = severity_emoji.get(note.severity.value, "❓")
    
    print(f"{emoji} [{note.severity.value.upper()}] AI Finding #{index}")
    print(f"{'─' * 75}")
    print(f"📋 Issue:")
    print(f"   {note.issue}")
    print()
    print(f"🧠 AI Reasoning:")
    print(f"   {note.reasoning}")
    print()
    
    if note.affected_orders:
        print(f"📝 Affected Orders: {', '.join(note.affected_orders)}")
        print()
    
    print(f"💡 AI Recommendations:")
    for i, rec in enumerate(note.recommendations, 1):
        print(f"   {i}. {rec}")
    print()
    
    if note.guideline_reference:
        print(f"📚 Guideline Reference: {note.guideline_reference}")
    
    if note.requires_human_review:
        print(f"   ⚡ AI flags this for mandatory human review")
    
    print()


def print_validation_summary(result):
    """Print summary of AI validation results."""
    print(f"🤖 AI-Powered Validation Results")
    print(f"{'─' * 80}")
    print(f"Patient ID: {result.patient_id}")
    print(f"Timestamp: {result.check_timestamp}")
    print(f"Overall Severity: {result.overall_severity.value.upper()}")
    print(f"\n📊 AI Analysis Summary:")
    print(f"   {result.summary}")
    print(f"\n📈 Findings Breakdown:")
    print(f"   Total Issues Found: {result.total_issues_found}")
    print(f"   🚨 Critical: {result.critical_count}")
    print(f"   ⚠️  High: {result.high_count}")
    print(f"   🟡 Moderate: {result.moderate_count}")
    print(f"   🔵 Low/Routine: {result.routine_count}")
    
    if result.requires_urgent_review:
        print(f"\n⚡ ⚡ ⚡ URGENT CLINICAL REVIEW REQUIRED ⚡ ⚡ ⚡")
    
    print(f"\n📚 Guidelines Consulted by AI:")
    for guideline in result.guidelines_consulted:
        print(f"   • {guideline}")


async def test_patient_with_ai(patient_id: str, show_details: bool = True):
    """Test AI-powered validation for a specific patient."""
    
    print_separator(f"AI Analysis: Patient {patient_id}")
    
    # Get patient data
    patient_data = get_patient_data(patient_id)
    
    if not patient_data:
        print(f"❌ Patient {patient_id} not found!")
        return
    
    # Show patient details
    if show_details:
        patient = patient_data["patient"]
        print(f"👤 Patient Information:")
        print(f"   Age: {patient['age']}, Gender: {patient['gender']}")
        print(f"   Diagnosis: {patient['current_diagnosis']}")
        print(f"   Department: {patient['department']}")
        print(f"   Allergies: {', '.join(patient['allergies'])}")
        print(f"   Comorbidities: {', '.join(patient['comorbidities'])}")
        
        vitals = patient['vitals']
        print(f"\n📊 Current Vitals:")
        print(f"   BP: {vitals['bp_systolic']}/{vitals['bp_diastolic']} mmHg")
        print(f"   HR: {vitals['heart_rate']} bpm")
        print(f"   RR: {vitals['respiratory_rate']}/min")
        print(f"   SpO2: {vitals['spo2']}%")
        print(f"   Temp: {vitals['temperature_c']}°C")
        
        print(f"\n💊 Active Medications:")
        for med in patient_data["active_orders"].get("medications", []):
            print(f"   • {med['medication']} {med['dose']} {med['route']} {med['frequency']}")
            print(f"     Indication: {med.get('indication', 'Not specified')}")
        
        print()
    
    # Initialize AI validator
    if not openai_guideline_validator.initialized:
        print("🤖 Initializing OpenAI-powered validator...")
        openai_guideline_validator.initialize()
    
    # Perform AI validation
    print("🔍 Sending patient data to OpenAI for intelligent analysis...")
    print("   (This may take 10-30 seconds for AI reasoning...)")
    
    start_time = datetime.now()
    
    try:
        result = await openai_guideline_validator.validate_orders(
            patient_id=patient_id,
            active_orders=patient_data["active_orders"],
            clinical_context=patient_data["clinical_context"],
            patient_record=patient_data["patient"],
            specialty=patient_data["patient"]["department"]
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"✅ AI analysis complete in {duration:.1f} seconds")
        
    except Exception as e:
        print(f"\n❌ Error during AI validation: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    print_separator("AI Validation Results")
    
    # Print summary
    print_validation_summary(result)
    
    # Print detailed AI-generated notes
    if result.medical_notes:
        print_separator("Detailed AI-Generated Medical Notes")
        for i, note in enumerate(result.medical_notes, 1):
            print_ai_note(note, i)
    else:
        print("\n✅ AI Analysis: No issues found! All orders align with guidelines.")
    
    # Print disclaimer
    print_separator()
    print("⚠️  AI SAFETY DISCLAIMER:")
    print(result.safety_disclaimer)
    
    return result


async def quick_ai_test():
    """Quick test with the most complex case (P003 - Septic Shock)."""
    
    print_separator("QUICK AI TEST: Patient P003 (Septic Shock)")
    print("This is the most complex case - AI should find multiple CRITICAL findings.\n")
    
    await test_patient_with_ai("P003", show_details=True)


async def compare_all_patients():
    """Run AI analysis on all patients and compare severity."""
    
    print_separator("AI COMPARISON: All Sample Patients")
    
    patient_ids = list_all_patients()
    results = []
    
    # Initialize validator once
    if not openai_guideline_validator.initialized:
        openai_guideline_validator.initialize()
    
    print(f"Running AI analysis on {len(patient_ids)} patients...\n")
    
    for i, patient_id in enumerate(patient_ids, 1):
        print(f"[{i}/{len(patient_ids)}] Analyzing {patient_id}...", end=" ", flush=True)
        
        patient_data = get_patient_data(patient_id)
        
        try:
            result = await openai_guideline_validator.validate_orders(
                patient_id=patient_id,
                active_orders=patient_data["active_orders"],
                clinical_context=patient_data["clinical_context"],
                patient_record=patient_data["patient"],
                specialty=patient_data["patient"]["department"]
            )
            
            print(f"✅ Complete ({result.total_issues_found} issues)")
            
            results.append({
                "patient_id": patient_id,
                "diagnosis": patient_data["patient"]["current_diagnosis"],
                "department": patient_data["patient"]["department"],
                "total_issues": result.total_issues_found,
                "critical": result.critical_count,
                "high": result.high_count,
                "moderate": result.moderate_count,
                "severity": result.overall_severity.value,
                "urgent_review": result.requires_urgent_review
            })
            
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Print comparison table
    print(f"\n{'='*100}")
    print("AI ANALYSIS COMPARISON TABLE")
    print(f"{'='*100}")
    print(f"{'Patient':<10} {'Diagnosis':<30} {'Dept':<12} {'Total':<7} {'🚨':<5} {'⚠️':<5} {'🟡':<5} {'Urgent?':<8}")
    print("-" * 100)
    
    for r in results:
        urgent = "YES" if r["urgent_review"] else "No"
        print(f"{r['patient_id']:<10} {r['diagnosis']:<30} {r['department']:<12} {r['total_issues']:<7} {r['critical']:<5} {r['high']:<5} {r['moderate']:<5} {urgent:<8}")
    
    print()


async def interactive_ai_demo():
    """Interactive demo showing AI reasoning process."""
    
    print_separator("INTERACTIVE AI DEMO")
    print("Watch the AI analyze a complex septic shock case step-by-step.")
    print()
    
    patient_id = "P003"
    patient_data = get_patient_data(patient_id)
    
    print("Step 1: Patient Presentation")
    print("─" * 80)
    context = patient_data["clinical_context"]
    print(f"Presentation: {context['presentation']}")
    print(f"Working Diagnosis: {context['working_diagnosis']}")
    print(f"Vitals: BP 82/48, HR 128, Lactate 4.8 mmol/L")
    print()
    
    input("Press Enter to continue...")
    
    print("\nStep 2: Active Orders Review")
    print("─" * 80)
    print("Current orders:")
    for med in patient_data["active_orders"]["medications"]:
        print(f"  • {med['medication']} {med['dose']}")
    print()
    
    input("Press Enter to send to AI for analysis...")
    
    print("\nStep 3: AI Retrieves Relevant Guidelines")
    print("─" * 80)
    print("🔍 Searching guideline database for 'Septic shock treatment protocol'...")
    print("✅ Retrieved: Surviving Sepsis Campaign 2021 Guidelines")
    print("✅ Retrieved: Hour-1 Bundle Requirements")
    print()
    
    input("Press Enter to continue...")
    
    print("\nStep 4: AI Reasoning (GPT-4 Analysis)")
    print("─" * 80)
    print("🤖 Sending patient data + guidelines to OpenAI...")
    print("🧠 AI is analyzing...")
    
    # Actually run the AI analysis
    result = await test_patient_with_ai(patient_id, show_details=False)
    
    print("\n✅ AI analysis complete!")
    print(f"Found {result.total_issues_found} issues requiring attention.")
    

async def runtime_benchmark_test(
    patient_id: str = "P003",
    runs: int = 10,
    warmup_runs: int = 1,
    min_seconds: float = 5.0,
    max_seconds: float = 15.0
):
    """
    Runtime benchmark for AI validation.
    Ensures average runtime stays within 5–15 seconds.
    """

    print_separator("AI RUNTIME BENCHMARK TEST")
    print(f"Patient: {patient_id}")
    print(f"Runs: {runs} (warm-up: {warmup_runs})")
    print(f"Expected average runtime: {min_seconds}-{max_seconds} seconds\n")

    patient_data = get_patient_data(patient_id)
    if not patient_data:
        print(f"❌ Patient {patient_id} not found!")
        return

    if not openai_guideline_validator.initialized:
        print("🤖 Initializing OpenAI-powered validator...")
        openai_guideline_validator.initialize()

    timings = []

    for i in range(runs):
        print(f"⏱️  Run {i + 1}/{runs}...", end=" ", flush=True)

        start = datetime.now()

        await openai_guideline_validator.validate_orders(
            patient_id=patient_id,
            active_orders=patient_data["active_orders"],
            clinical_context=patient_data["clinical_context"],
            patient_record=patient_data["patient"],
            specialty=patient_data["patient"]["department"]
        )

        duration = (datetime.now() - start).total_seconds()
        timings.append(duration)

        label = "warm-up" if i < warmup_runs else "measured"
        print(f"{duration:.2f}s ({label})")

    measured = timings[warmup_runs:]
    avg_runtime = sum(measured) / len(measured)

    print("\n📊 BENCHMARK RESULTS")
    print("─" * 80)
    for i, t in enumerate(timings):
        label = "warm-up" if i < warmup_runs else "measured"
        print(f"Run {i + 1}: {t:.2f}s ({label})")

    print(f"\n📈 Average runtime (measured): {avg_runtime:.2f}s")

    if min_seconds <= avg_runtime <= max_seconds:
        print("✅ BENCHMARK PASSED")
        print(f"   Runtime within expected range ({min_seconds}-{max_seconds}s)")
    else:
        print("❌ BENCHMARK FAILED")
        print(
            f"   Average runtime {avg_runtime:.2f}s is outside "
            f"expected range ({min_seconds}-{max_seconds}s)"
        )



def main():
    """Main test menu."""
    
    print("\n" + "="*80)
    print("  🤖 OPENAI-POWERED MEDICAL GUIDELINE VALIDATION - TEST SUITE")
    print("="*80)
    
    # Check API key
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        print(f"✅ OpenAI API Key: {api_key[:15]}...{api_key[-4:]}")
    else:
        print("❌ OpenAI API Key: NOT SET")
        return
    
    print("\nSelect a test option:")
    print("  1. Quick AI test (Patient P003 - Septic Shock)")
    print("  2. Test specific patient")
    print("  3. Compare all patients (AI analysis)")
    print("  4. Interactive AI demo (step-by-step)")
    print("  5. Benchmark runtime")
    print("  6. Exit")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        asyncio.run(quick_ai_test())
    
    elif choice == "2":
        patient_ids = list_all_patients()
        print(f"\nAvailable patients: {', '.join(patient_ids)}")
        patient_id = input("Enter patient ID: ").strip().upper()
        
        if patient_id in patient_ids:
            asyncio.run(test_patient_with_ai(patient_id))
        else:
            print(f"❌ Patient {patient_id} not found!")
    
    elif choice == "3":
        asyncio.run(compare_all_patients())
    
    elif choice == "4":
        asyncio.run(interactive_ai_demo())
    
    elif choice == "5":
        asyncio.run(runtime_benchmark_test())

    elif choice == "6":
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