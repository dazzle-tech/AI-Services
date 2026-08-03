"""Service configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


@dataclass
class Settings:
    host: str
    port: int

    whisper_model: str
    whisper_device: str  # "auto" | "cuda" | "cpu"
    whisper_compute_type: Optional[str]
    whisper_language: Optional[str]
    whisper_model_cache: Optional[str]

    radiology_prompt_path: Path
    stream_chunk_seconds: float
    stream_overlap_seconds: float
    max_upload_mb: int

    api_root: Path

    @classmethod
    def load(cls) -> "Settings":
        api_root = Path(__file__).resolve().parent.parent
        prompt_path = Path(_env("RADIOLOGY_PROMPT_PATH", "prompts/radiology_lexicon.txt"))
        if not prompt_path.is_absolute():
            prompt_path = api_root / prompt_path

        return cls(
            host=_env("HOST", "0.0.0.0"),
            port=int(_env("PORT", "8013")),
            whisper_model=_env("WHISPER_MODEL", "medium"),
            whisper_device=_env("WHISPER_DEVICE", "auto").lower(),
            whisper_compute_type=_env("WHISPER_COMPUTE_TYPE"),
            whisper_language=_env("WHISPER_LANGUAGE", "en"),
            whisper_model_cache=_env("WHISPER_MODEL_CACHE"),
            radiology_prompt_path=prompt_path,
            stream_chunk_seconds=float(_env("STREAM_CHUNK_SECONDS", "4.0")),
            stream_overlap_seconds=float(_env("STREAM_OVERLAP_SECONDS", "0.5")),
            max_upload_mb=int(_env("MAX_UPLOAD_MB", "200")),
            api_root=api_root,
        )

    def load_radiology_prompt(self) -> str:
        try:
            return self.radiology_prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""
