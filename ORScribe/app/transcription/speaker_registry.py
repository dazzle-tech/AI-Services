"""Cross-chunk speaker label consistency."""

from __future__ import annotations

from typing import Dict, List

from app.transcription.base import DiarizedSegment


class SpeakerRegistry:
    """
    Maps per-chunk diarization labels to global SPEAKER_XX labels
    so the same physical speaker keeps the same label across chunks.
    """

    def __init__(self, registry: Dict[str, str] | None = None) -> None:
        self._global_to_local_history: Dict[str, str] = dict(registry or {})
        self._next_index = self._compute_next_index()

    def _compute_next_index(self) -> int:
        indices = []
        for label in self._global_to_local_history:
            if label.startswith("SPEAKER_"):
                try:
                    indices.append(int(label.split("_")[1]))
                except (IndexError, ValueError):
                    pass
        return max(indices, default=-1) + 1

    def map_chunk_segments(
        self,
        segments: List[DiarizedSegment],
        chunk_local_labels: List[str],
    ) -> List[DiarizedSegment]:
        """Remap chunk-local speaker labels to global labels."""
        mapping = self._build_mapping(chunk_local_labels)
        return [
            DiarizedSegment(
                speaker_label=mapping.get(seg.speaker_label, seg.speaker_label),
                start_time=seg.start_time,
                end_time=seg.end_time,
                text=seg.text,
            )
            for seg in segments
        ]

    def _build_mapping(self, chunk_local_labels: List[str]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        used_globals = set(self._global_to_local_history.keys())

        for local_label in sorted(set(chunk_local_labels)):
            if local_label in self._global_to_local_history.values():
                for global_label, stored_local in self._global_to_local_history.items():
                    if stored_local == local_label:
                        mapping[local_label] = global_label
                        break
                continue

            # Assign next available global label
            global_label = f"SPEAKER_{self._next_index:02d}"
            self._next_index += 1
            self._global_to_local_history[global_label] = local_label
            mapping[local_label] = global_label
            used_globals.add(global_label)

        return mapping

    def to_dict(self) -> Dict[str, str]:
        return dict(self._global_to_local_history)

    @classmethod
    def from_dict(cls, data: Dict[str, str] | None) -> SpeakerRegistry:
        return cls(registry=data)
