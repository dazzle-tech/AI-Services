"""Speak the chest-pain dictation sample to samples/chest_pain_summary.wav."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "samples" / "chest_pain_summary.wav"
DICTATION = (
    "Patient is a 65 year old male presenting with acute chest pain that started 2 hours ago. "
    "Blood pressure is 150 over 90. Heart rate 95 beats per minute. "
    "Patient has a history of hypertension and is currently taking Lisinopril 10 milligrams daily. "
    "No known allergies. "
    "Assessment, possible acute coronary syndrome. "
    "Plan, EKG, cardiac enzymes, aspirin 325 milligrams."
)


def _voices() -> list[str]:
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )
    voices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not voices:
        raise RuntimeError("No Windows speech voices are installed")
    return voices


def _speak(text: str, output: Path, voice: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    escaped_text = text.replace('"', '`"')
    script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = -1
$s.SelectVoice('{voice.replace("'", "''")}')
$s.SetOutputToWaveFile('{str(output).replace("'", "''")}')
$s.Speak("{escaped_text}")
$s.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def main() -> None:
    voices = _voices()
    preferred = next((name for name in voices if "David" in name or "Zira" in name), voices[0])
    _speak(DICTATION, OUTPUT, preferred)
    print(f"Wrote {OUTPUT} using voice {preferred}")


if __name__ == "__main__":
    main()
