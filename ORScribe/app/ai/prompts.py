"""LLM prompt helpers for OR conversation intelligence."""


def format_diarized_transcript(segments: list[dict], role_map: dict | None = None) -> str:
    lines = []
    for segment in segments:
        speaker = segment["speaker_label"]
        if role_map and speaker in role_map:
            role_entry = role_map[speaker]
            role = role_entry.get("role", role_entry) if isinstance(role_entry, dict) else role_entry
            speaker = f"{speaker} ({role})"
        start = segment["start_time"]
        hours = int(start // 3600)
        minutes = int((start % 3600) // 60)
        seconds = int(start % 60)
        timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        lines.append(f"[{timestamp}] {speaker}: {segment['text']}")
    return "\n".join(lines)
