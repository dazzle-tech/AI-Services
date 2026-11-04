"""Match structured field values back to the OCR lines they were read from."""
from __future__ import annotations

import re

from app.models.schemas import Box, FieldPosition, OCRLineOut
from app.services.ocr_service import OCRLine

_MISSING = {"undefined", "null", "none", ""}
_STOP = {"of", "the", "a", "and"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()


def _tokens(text: str) -> list[str]:
    return [token for token in _norm(text).split() if token not in _STOP]


def _label_hits(field_name: str, label: str) -> int:
    name_tokens = _tokens(field_name)
    label_tokens = set(_tokens(label))
    return sum(1 for token in name_tokens if token in label_tokens)


def _value_line_indexes(value_norm: str, lines: list[OCRLine]) -> list[int]:
    exact: list[int] = []
    contained: list[int] = []
    pattern = re.compile(rf"(?:^| ){re.escape(value_norm)}(?:$| )")
    for index, line in enumerate(lines):
        line_norm = _norm(line.text)
        if not line_norm:
            continue
        if line_norm == value_norm:
            exact.append(index)
        elif len(value_norm) >= 4 and pattern.search(line_norm):
            contained.append(index)
    return exact or contained


def _best_index(field_name: str, candidates: list[int], lines: list[OCRLine]) -> int:
    def score(index: int) -> tuple[int, int]:
        previous = lines[index - 1].text if index else ""
        hits = max(_label_hits(field_name, lines[index].text), _label_hits(field_name, previous))
        return hits, -index

    return max(candidates, key=score)


def _union_box(indexes: list[int], lines: list[OCRLine]) -> tuple[Box | None, bool]:
    if not indexes or any(not lines[index].box_valid for index in indexes):
        return None, False
    x0 = min(lines[index].box[0] for index in indexes)
    y0 = min(lines[index].box[1] for index in indexes)
    x1 = max(lines[index].box[0] + lines[index].box[2] for index in indexes)
    y1 = max(lines[index].box[1] + lines[index].box[3] for index in indexes)
    return Box(x=round(x0, 4), y=round(y0, 4), w=round(x1 - x0, 4), h=round(y1 - y0, 4)), True


def locate_field_positions(
    structured_data: dict,
    lines: list[OCRLine],
    *,
    include_boxes: bool,
) -> dict[str, FieldPosition]:
    """One position per string field. Missing or unmatched values are not drawable."""
    positions: dict[str, FieldPosition] = {}
    for name, value in structured_data.items():
        if not isinstance(value, str):
            continue
        value_norm = _norm(value)
        if value_norm in _MISSING:
            positions[name] = FieldPosition()
            continue
        candidates = _value_line_indexes(value_norm, lines)
        if not candidates:
            positions[name] = FieldPosition()
            continue
        chosen = _best_index(name, candidates, lines)
        indexes = [chosen]
        if chosen > 0 and _label_hits(name, lines[chosen - 1].text) > 0:
            indexes = [chosen - 1, chosen]
        box, box_valid = _union_box(indexes, lines) if include_boxes else (None, False)
        positions[name] = FieldPosition(
            line_indices=indexes,
            box=box,
            box_valid=box_valid,
        )
    return positions


def lines_out(lines: list[OCRLine]) -> list[OCRLineOut]:
    return [
        OCRLineOut(
            index=index,
            text=line.text,
            confidence=line.confidence,
            box=Box(x=line.box[0], y=line.box[1], w=line.box[2], h=line.box[3]),
            box_valid=line.box_valid,
            uncertain=line.uncertain,
        )
        for index, line in enumerate(lines)
    ]
