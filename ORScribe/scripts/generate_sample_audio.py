"""Generate a multi-speaker OR sample WAV for local testing."""

from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "samples" / "or_case_sample.wav"

SEGMENTS = [
    ("SPEAKER_00", "Sign in complete. Patient identity confirmed, site marked."),
    ("SPEAKER_01", "Anesthesia plan reviewed. Allergies noted. Consent verified."),
    ("SPEAKER_02", "Time out. Team introductions. Anticipated critical events reviewed."),
    ("SPEAKER_00", "Making incision now. Scalpel."),
    ("SPEAKER_01", "Blood pressure 120 over 80. Heart rate 72. Giving propofol 100 milligrams."),
    ("SPEAKER_02", "Sponge count correct. Instrument count correct."),
    (
        "SPEAKER_00",
        "Sign out. Procedure recorded as laparoscopic cholecystectomy. Specimen labeled.",
    ),
]

PAUSE_MS = 500


def _fallback_silent_wav(output: Path, duration_seconds: float = 55.0) -> None:
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


def _powershell_synthesize(text: str, output: Path, voice: str) -> None:
    escaped_text = text.replace('"', '`"')
    escaped_voice = voice.replace('"', '`"')
    escaped_output = str(output).replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = 0
$s.SelectVoice('{escaped_voice}')
$s.SetOutputToWaveFile('{escaped_output}')
$s.Speak("{escaped_text}")
$s.Dispose()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
    )


def _synthesize_with_sapi(output: Path) -> None:
    tmp_dir = output.parent / ".tmp_segments"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    voices = _powershell_voices()
    speaker_voice = {
        "SPEAKER_00": voices[0],
        "SPEAKER_01": voices[1 % len(voices)],
        "SPEAKER_02": voices[2 % len(voices)],
    }

    part_paths: list[Path] = []
    for index, (speaker, text) in enumerate(SEGMENTS):
        part_path = tmp_dir / f"seg_{index:02d}.wav"
        _powershell_synthesize(text, part_path, speaker_voice[speaker])
        part_paths.append(part_path)

    _concat_wavs(part_paths, output, PAUSE_MS)

    for part in part_paths:
        part.unlink(missing_ok=True)
    tmp_dir.rmdir()


def _concat_wavs(wav_paths: list[Path], output: Path, pause_ms: int) -> None:
    frames: list[bytes] = []
    sample_rate = 16000
    sample_width = 2
    silence_frames = int(sample_rate * pause_ms / 1000)
    silence = b"\x00\x00" * silence_frames

    for index, wav_path in enumerate(wav_paths):
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            frames.append(wav.readframes(wav.getnframes()))
        if index < len(wav_paths) - 1:
            frames.append(silence)

    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(sample_width)
        out.setframerate(sample_rate)
        out.writeframes(b"".join(frames))


def main() -> None:
    try:
        if sys.platform == "win32":
            _synthesize_with_sapi(OUTPUT)
        else:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", 165)
            voice_pool = engine.getProperty("voices") or []
            if not voice_pool:
                raise RuntimeError("No TTS voices available")
            tmp_dir = OUTPUT.parent / ".tmp_segments"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            speaker_voice = {
                "SPEAKER_00": voice_pool[0],
                "SPEAKER_01": voice_pool[1 % len(voice_pool)],
                "SPEAKER_02": voice_pool[2 % len(voice_pool)],
            }
            part_paths: list[Path] = []
            for index, (speaker, text) in enumerate(SEGMENTS):
                part_path = tmp_dir / f"seg_{index:02d}.wav"
                engine.setProperty("voice", speaker_voice[speaker].id)
                engine.save_to_file(text, str(part_path))
                engine.runAndWait()
                part_paths.append(part_path)
            _concat_wavs(part_paths, OUTPUT, PAUSE_MS)
            for part in part_paths:
                part.unlink(missing_ok=True)
            tmp_dir.rmdir()

        with wave.open(str(OUTPUT), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        print(f"Wrote {OUTPUT} ({duration:.1f}s, {OUTPUT.stat().st_size // 1024} KB)")
    except Exception as exc:
        print(f"TTS failed ({exc}) — writing silent placeholder", file=sys.stderr)
        _fallback_silent_wav(OUTPUT)


if __name__ == "__main__":
    main()
