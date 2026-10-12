"""Prompt helpers for role-tagged transcripts."""


def format_diarized_transcript(segments: list[dict]) -> str:
    lines = []
    for segment in segments:
        lines.append(f"{segment['speaker_label']}: {segment['text']}")
    return "\n".join(lines)


def format_role_tagged_transcript(segments: list[dict], role_map: dict[str, str]) -> str:
    lines = []
    for segment in segments:
        role = role_map.get(segment["speaker_label"], "other")
        lines.append(f"{role}: {segment['text']}")
    return "\n".join(lines)
