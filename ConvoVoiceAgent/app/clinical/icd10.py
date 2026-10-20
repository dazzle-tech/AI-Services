"""Local ICD-10-CM table. A code that is not in this table is never returned."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_TABLE_PATH = Path(__file__).with_name("icd10_codes.json")


@dataclass(frozen=True)
class Icd10Entry:
    code: str
    label: str
    chronic: bool
    synonyms: tuple[str, ...]


def normalize_code(code: str | None) -> str:
    return re.sub(r"\s+", "", str(code or "")).upper()


@lru_cache(maxsize=1)
def load_table() -> dict[str, Icd10Entry]:
    rows = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    table: dict[str, Icd10Entry] = {}
    for row in rows:
        code = normalize_code(row["code"])
        table[code] = Icd10Entry(
            code=code,
            label=row["label"],
            chronic=bool(row.get("chronic", False)),
            synonyms=tuple(row.get("synonyms", [])),
        )
    return table


def lookup(code: str | None) -> Icd10Entry | None:
    return load_table().get(normalize_code(code))


def find_by_text(text: str) -> list[Icd10Entry]:
    """Entries whose label or a synonym appears as a whole phrase in text."""
    lowered = text.lower()
    found: list[Icd10Entry] = []
    for entry in load_table().values():
        for phrase in (entry.label, *entry.synonyms):
            if re.search(rf"(?<!\w){re.escape(phrase.lower())}(?!\w)", lowered):
                found.append(entry)
                break
    return found


def prompt_table() -> str:
    return "\n".join(f"{entry.code}\t{entry.label}" for entry in load_table().values())
