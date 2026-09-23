"""CSV text extraction (stdlib csv -- no new dependency needed)."""
from __future__ import annotations

import csv
import io

MIN_ROWS = 1


def extract_csv_text(file_bytes: bytes) -> str:
    """Render a CSV file's rows into a readable pipe-delimited text block.

    Raises:
        ValueError: If the file cannot be decoded/parsed as CSV, or has no rows.
    """
    try:
        decoded = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            decoded = file_bytes.decode("latin-1")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Unreadable or corrupted CSV file: {exc}") from exc

    try:
        reader = csv.reader(io.StringIO(decoded))
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise ValueError(f"Unreadable or corrupted CSV file: {exc}") from exc

    if len(rows) < MIN_ROWS:
        raise ValueError("No rows found in CSV file")

    lines = [" | ".join(cell.strip() for cell in row) for row in rows]
    return "\n".join(lines)
