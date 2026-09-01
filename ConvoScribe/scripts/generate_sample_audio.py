"""Generate doctor–patient visit WAVs for local testing.

Writes:
  samples/visit_sample.wav          — sequential two-speaker visit
  samples/visit_overlap_sample.wav  — three-speaker visit with overlapping speech
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


def _synthesize_simple(output: Path, voices: list[str]) -> None:
    tmp_dir = output.parent / ".tmp_segments"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    speaker_voice = _speaker_voices(voices)
    rates = _speaker_rates()

    part_paths: list[Path] = []
    for index, (speaker, text) in enumerate(SIMPLE_SEGMENTS):
        part_path = tmp_dir / f"simple_{index:02d}.wav"
        _powershell_synthesize(text, part_path, speaker_voice[speaker], rates[speaker])
        part_paths.append(part_path)

    _concat_wavs(part_paths, output, SIMPLE_PAUSE_MS)
    for part in part_paths:
        part.unlink(missing_ok=True)
    tmp_dir.rmdir()


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
    except Exception as exc:
        print(f"TTS failed ({exc}) — writing silent placeholders", file=sys.stderr)
        _fallback_silent_wav(SIMPLE_OUTPUT)
        _fallback_silent_wav(OVERLAP_OUTPUT, duration_seconds=50.0)


if __name__ == "__main__":
    main()
