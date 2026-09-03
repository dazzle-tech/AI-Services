"""Generate doctor–patient visit WAVs for local testing.

Writes:
  samples/visit_sample.wav          — sequential two-speaker visit
  samples/visit_overlap_sample.wav  — three-speaker visit with overlapping speech
  samples/visit_3min_sample.wav     — sequential GP visit lasting at least 3 minutes
"""

from __future__ import annotations

import array
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIMPLE_OUTPUT = ROOT / "samples" / "visit_sample.wav"
OVERLAP_OUTPUT = ROOT / "samples" / "visit_overlap_sample.wav"
LONG_OUTPUT = ROOT / "samples" / "visit_3min_sample.wav"
LONG_TRANSCRIPT = ROOT / "samples" / "visit_3min_sample.txt"
LONG_MIN_SECONDS = 180.0

# Doctor (SPEAKER_00) and patient (SPEAKER_01) — matches stub transcription text.
SIMPLE_SEGMENTS = [
    ("SPEAKER_00", "Good morning. What brings you in today?"),
    ("SPEAKER_01", "I've had a sore throat and fever for three days."),
    (
        "SPEAKER_00",
        "Any difficulty swallowing? I'll examine your throat and check your temperature.",
    ),
    ("SPEAKER_01", "Swallowing hurts a little. No other symptoms."),
    (
        "SPEAKER_00",
        "Likely viral pharyngitis. Rest, fluids, acetaminophen as needed. Follow up if worsening.",
    ),
]

# Full GP visit (doctor SPEAKER_00, patient SPEAKER_01). Spoken length is padded to >= 3 minutes.
LONG_SEGMENTS = [
    ("SPEAKER_00", "Good morning, I am Doctor Chen. Please have a seat. What brings you in today?"),
    ("SPEAKER_01", "Good morning, doctor. I am Maria Lopez. I have had a tight pressure in the center of my chest for three days, and I get short of breath walking to the mailbox."),
    ("SPEAKER_00", "I am sorry you have been dealing with that. On a scale from zero to ten, how strong is the pressure at its worst?"),
    ("SPEAKER_01", "At rest it is about a three. When I walk or climb stairs it goes up to a six, and it lasts maybe ten minutes after I stop."),
    ("SPEAKER_00", "Does the pressure move into your jaw, neck, back, or either arm?"),
    ("SPEAKER_01", "Sometimes into my left shoulder, not into the jaw. It does not feel sharp. It feels like someone is sitting on my chest."),
    ("SPEAKER_00", "Any sweating, nausea, dizziness, or a feeling that you might pass out when it happens?"),
    ("SPEAKER_01", "I got clammy yesterday after lunch. No vomiting. I sat down and it eased. I did not call emergency services because it went away."),
    ("SPEAKER_00", "That was still the right time to be seen. When did this first start, and have you had similar pain before?"),
    ("SPEAKER_01", "It started Monday evening while I was washing dishes. I had a milder ache last winter that I blamed on indigestion. This feels different and more persistent."),
    ("SPEAKER_00", "Are you still smoking, and how much alcohol do you drink in a typical week?"),
    ("SPEAKER_01", "I quit cigarettes two years ago after twenty years. I have one glass of wine on Friday. I do not use other tobacco."),
    ("SPEAKER_00", "Tell me about your medical history, especially heart, blood pressure, diabetes, and cholesterol."),
    ("SPEAKER_01", "I have type two diabetes for eight years, high blood pressure, and high cholesterol. I had my gallbladder out in twenty nineteen. No heart attack and no stent that I know of."),
    ("SPEAKER_00", "What medicines are you taking, including doses if you remember them?"),
    ("SPEAKER_01", "Metformin five hundred milligrams twice a day, lisinopril ten milligrams in the morning, atorvastatin twenty milligrams at night, and aspirin eighty one milligrams daily. I also take vitamin D."),
    ("SPEAKER_00", "Any drug allergies, and have you missed any of those medicines this week?"),
    ("SPEAKER_01", "I get a rash with penicillin. I missed atorvastatin two nights because I ran out. I took the rest on schedule. I have been under a lot of work stress."),
    ("SPEAKER_00", "Thank you. Any cough, fever, leg swelling, or pain in the calves?"),
    ("SPEAKER_01", "No fever. A dry cough at night for a week. My ankles look a bit puffy by evening. No calf pain. I sleep on two pillows now."),
    ("SPEAKER_00", "That is helpful. I am going to examine you. Blood pressure today is one hundred fifty two over ninety two, heart rate eighty eight and regular, oxygen ninety six percent on room air, temperature thirty six point eight."),
    ("SPEAKER_01", "That blood pressure is higher than at home. At home it is usually around one thirty over eighty."),
    ("SPEAKER_00", "Your heart sounds have no murmur. Lungs are clear. There is mild ankle swelling. Abdomen is soft. I do not hear a carotid bruit."),
    ("SPEAKER_01", "So you do not think this is just anxiety from work?"),
    ("SPEAKER_00", "Stress can add strain, but with diabetes, missed statin, exertional chest pressure, and radiation to the shoulder, I am treating this as possible angina until we prove otherwise."),
    ("SPEAKER_01", "That scares me. Do I need to go to the hospital right now?"),
    ("SPEAKER_00", "You are stable in clinic, but we will not send you home without an electrocardiogram and blood work today. If the tracing or troponin is concerning, we transfer you to the emergency department."),
    ("SPEAKER_01", "Alright. What happens if those tests are okay?"),
    ("SPEAKER_00", "Then I will start a low dose of aspirin if you are not already taking it, which you are, continue the statin without gaps, and refer you for an urgent stress test or cardiology clinic this week."),
    ("SPEAKER_01", "Can I keep walking my dog? She is small but the hill on our street is steep."),
    ("SPEAKER_00", "Please avoid hills, heavy lifting, and exercise that brings on the pressure until cardiology sees you. Flat slow walking is fine if you stop at the first hint of tightness."),
    ("SPEAKER_01", "What about work? I sit at a desk but I get stressed, and I drive forty minutes each way."),
    ("SPEAKER_00", "Desk work is acceptable if you feel well. If the pressure returns, lasts more than five minutes, or comes with sweating or nausea, call emergency services. Do not drive yourself."),
    ("SPEAKER_01", "Should I change any of my pills today? My sister said I should take extra aspirin."),
    ("SPEAKER_00", "Do not take extra aspirin on your own. Stay on eighty one milligrams daily. Restart atorvastatin tonight. I will write a refill. Continue metformin and lisinopril."),
    ("SPEAKER_01", "Is there anything I can eat or drink that makes this worse? I had a large coffee this morning."),
    ("SPEAKER_00", "Limit extra caffeine if it makes your heart race. Keep meals moderate. Watch salt because of the ankle swelling. Check fingerstick sugars as usual."),
    ("SPEAKER_01", "My last A one C was seven point eight in March. I have been snacking more at night."),
    ("SPEAKER_00", "We will recheck A one C with labs today. After the chest issue is sorted, we can tighten diabetes control. One problem at a time so we do not miss the heart."),
    ("SPEAKER_01", "Who do I call with questions after I leave, and when do I come back?"),
    ("SPEAKER_00", "The nurse will give you the clinic number. If tests today are reassuring, follow up with me in two days and with cardiology within a week. We will call you with lab results."),
    ("SPEAKER_01", "Please tell my husband if I have to go across to the hospital. His name is Luis and he is in the waiting room."),
    ("SPEAKER_00", "We will keep Luis informed. Do you have any other questions before the electrocardiogram?"),
    ("SPEAKER_01", "Just one. If this is angina, does that mean I will need a stent?"),
    ("SPEAKER_00", "Not necessarily. Some people do well with medicines and risk reduction. Imaging or catheterization is only if the tests show a significant blockage or if symptoms worsen."),
    ("SPEAKER_01", "Okay. I understand. Thank you for explaining it clearly. I am ready for the electrocardiogram."),
    ("SPEAKER_00", "Good. Stay on the table. The technician will place the stickers. After that, the nurse draws blood for troponin, a metabolic panel, and A one C. I will review everything with you before you leave."),
]

# Timeline: start_ms is when this utterance begins on the mixed track.
# Overlaps are intentional (negative gap vs previous utterance duration).
OVERLAP_SEGMENTS = [
    (0, "SPEAKER_00", "Good afternoon. I'm Dr. Patel. What brings you in today?"),
    (4200, "SPEAKER_01", "I've had this tight pressure in my chest since yesterday, and I feel short of breath when I walk."),
    # Family member talks over the patient mid-sentence.
    (6200, "SPEAKER_02", "He also woke up sweating last night and he was clutching his arm."),
    # Doctor starts while both patient and family are still speaking.
    (9800, "SPEAKER_00", "Hold on, one at a time. Does the pain radiate to your jaw or left arm?"),
    (14500, "SPEAKER_01", "Yes, into my left arm, and I took two aspirin this morning."),
    # Family overlaps the aspirin detail.
    (16800, "SPEAKER_02", "No, it was three aspirin, and he has diabetes and high blood pressure."),
    (20500, "SPEAKER_00", "Any nitroglycerin at home? Are you on metformin and a statin?"),
    (23800, "SPEAKER_01", "Yes metformin, and atorvastatin, but I skipped it last week."),
    # Crosstalk: patient and family answer the same question together.
    (26800, "SPEAKER_02", "He skipped it because it made his legs ache."),
    (29200, "SPEAKER_00", "I'm going to get an EKG now. This could be unstable angina. Stay still."),
    (33800, "SPEAKER_01", "I'm scared. Don't let me"),
    # Doctor talks over the patient's fear.
    (35200, "SPEAKER_00", "You're in the right place. We will treat this as possible ACS until proven otherwise."),
    (40200, "SPEAKER_02", "Should I call our daughter? She has his medication list."),
    (42800, "SPEAKER_00", "Yes, please. Plan is aspirin, ECG, troponin, and cardiology consult."),
]

SIMPLE_PAUSE_MS = 600
LONG_PAUSE_MS = 900


def _fallback_silent_wav(output: Path, duration_seconds: float = 35.0) -> None:
    sample_rate = 16000
    num_frames = int(duration_seconds * sample_rate)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * num_frames)
    print(f"Wrote silent placeholder ({duration_seconds:.0f}s): {output}")


def _powershell_voices() -> list[str]:
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
        raise RuntimeError("No SAPI voices available")
    return voices


def _powershell_synthesize(text: str, output: Path, voice: str, rate: int = 0) -> None:
    escaped_text = text.replace('"', '`"')
    escaped_voice = voice.replace("'", "''")
    escaped_output = str(output).replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = {int(rate)}
$s.SelectVoice('{escaped_voice}')
$s.SetOutputToWaveFile('{escaped_output}')
$s.Speak("{escaped_text}")
$s.Dispose()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
    )


def _read_pcm(path: Path) -> tuple[int, int, array.array]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise RuntimeError(f"Expected 16-bit PCM, got {sample_width * 8}-bit: {path}")
    samples = array.array("h")
    samples.frombytes(frames)
    if channels > 1:
        samples = array.array("h", samples[::channels])
    return sample_rate, channels, samples


def _concat_wavs(wav_paths: list[Path], output: Path, pause_ms: int) -> None:
    frames: list[bytes] = []
    sample_rate = 16000
    sample_width = 2
    silence_frames = 0
    silence = b""

    for index, wav_path in enumerate(wav_paths):
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            if index == 0:
                silence_frames = int(sample_rate * pause_ms / 1000)
                silence = b"\x00\x00" * silence_frames
            frames.append(wav.readframes(wav.getnframes()))
        if index < len(wav_paths) - 1:
            frames.append(silence)

    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(sample_width)
        out.setframerate(sample_rate)
        out.writeframes(b"".join(frames))


def _mix_clips(
    clips: list[tuple[int, array.array]],
    sample_rate: int,
    output: Path,
) -> None:
    if not clips:
        raise RuntimeError("No clips to mix")

    end = max(start + len(samples) for start, samples in clips)
    mix = [0] * end
    for start, samples in clips:
        for offset, value in enumerate(samples):
            mix[start + offset] += int(value)

    clamped = array.array("h", (max(-32768, min(32767, value)) for value in mix))
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(clamped.tobytes())


def _speaker_voices(voices: list[str]) -> dict[str, str]:
    return {
        "SPEAKER_00": voices[0],
        "SPEAKER_01": voices[1 % len(voices)],
        "SPEAKER_02": voices[2 % len(voices)] if len(voices) > 2 else voices[0],
    }


def _speaker_rates() -> dict[str, int]:
    # Distinct rates make overlapping talkers easier to hear.
    return {"SPEAKER_00": -1, "SPEAKER_01": 1, "SPEAKER_02": 2}


def _pad_to_min_duration(output: Path, min_seconds: float) -> None:
    with wave.open(str(output), "rb") as wav:
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        channels = wav.getnchannels()
        frames = wav.readframes(wav.getnframes())
        duration = wav.getnframes() / sample_rate
    if duration >= min_seconds:
        return
    extra = int((min_seconds - duration) * sample_rate)
    silence = b"\x00" * extra * sample_width * channels
    with wave.open(str(output), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(sample_width)
        out.setframerate(sample_rate)
        out.writeframes(frames + silence)


def _write_transcript(segments: list[tuple[str, str]], output: Path) -> None:
    role = {"SPEAKER_00": "Doctor", "SPEAKER_01": "Patient"}
    lines = [f"{role.get(speaker, speaker)}: {text}" for speaker, text in segments]
    output.write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def _synthesize_sequential(
    segments: list[tuple[str, str]],
    output: Path,
    voices: list[str],
    pause_ms: int,
    tmp_prefix: str,
) -> None:
    tmp_dir = output.parent / f".tmp_{tmp_prefix}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    speaker_voice = _speaker_voices(voices)
    rates = _speaker_rates()

    part_paths: list[Path] = []
    for index, (speaker, text) in enumerate(segments):
        part_path = tmp_dir / f"{tmp_prefix}_{index:02d}.wav"
        _powershell_synthesize(text, part_path, speaker_voice[speaker], rates[speaker])
        part_paths.append(part_path)

    _concat_wavs(part_paths, output, pause_ms)
    for part in part_paths:
        part.unlink(missing_ok=True)
    tmp_dir.rmdir()


def _synthesize_simple(output: Path, voices: list[str]) -> None:
    _synthesize_sequential(SIMPLE_SEGMENTS, output, voices, SIMPLE_PAUSE_MS, "simple")


def _synthesize_overlap(output: Path, voices: list[str]) -> None:
    tmp_dir = output.parent / ".tmp_overlap"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    speaker_voice = _speaker_voices(voices)
    rates = _speaker_rates()

    part_paths: list[Path] = []
    for index, (_start_ms, speaker, text) in enumerate(OVERLAP_SEGMENTS):
        part_path = tmp_dir / f"ov_{index:02d}.wav"
        _powershell_synthesize(text, part_path, speaker_voice[speaker], rates[speaker])
        part_paths.append(part_path)

    sample_rate = None
    clips: list[tuple[int, array.array]] = []
    for (start_ms, _speaker, _text), part_path in zip(OVERLAP_SEGMENTS, part_paths):
        rate, _channels, samples = _read_pcm(part_path)
        if sample_rate is None:
            sample_rate = rate
        elif rate != sample_rate:
            raise RuntimeError(f"Mixed sample rates: {rate} vs {sample_rate}")
        start_sample = int(start_ms * sample_rate / 1000)
        clips.append((start_sample, samples))

    assert sample_rate is not None
    _mix_clips(clips, sample_rate, output)

    for part in part_paths:
        part.unlink(missing_ok=True)
    tmp_dir.rmdir()


def _write_duration(output: Path) -> None:
    with wave.open(str(output), "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
    print(f"Wrote {output} ({duration:.1f}s, {output.stat().st_size // 1024} KB)")


def main() -> None:
    try:
        if sys.platform != "win32":
            raise RuntimeError("Overlap mixer currently uses Windows SAPI")

        voices = _powershell_voices()
        _synthesize_simple(SIMPLE_OUTPUT, voices)
        _write_duration(SIMPLE_OUTPUT)
        _synthesize_overlap(OVERLAP_OUTPUT, voices)
        _write_duration(OVERLAP_OUTPUT)
        _synthesize_sequential(LONG_SEGMENTS, LONG_OUTPUT, voices, LONG_PAUSE_MS, "long")
        _pad_to_min_duration(LONG_OUTPUT, LONG_MIN_SECONDS)
        _write_transcript(LONG_SEGMENTS, LONG_TRANSCRIPT)
        _write_duration(LONG_OUTPUT)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "embed_3min_base64_postman.py")],
            check=True,
        )
    except Exception as exc:
        print(f"TTS failed ({exc}) — writing silent placeholders", file=sys.stderr)
        _fallback_silent_wav(SIMPLE_OUTPUT)
        _fallback_silent_wav(OVERLAP_OUTPUT, duration_seconds=50.0)
        _fallback_silent_wav(LONG_OUTPUT, duration_seconds=LONG_MIN_SECONDS)
        _write_transcript(LONG_SEGMENTS, LONG_TRANSCRIPT)


if __name__ == "__main__":
    main()
