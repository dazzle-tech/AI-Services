import re
from typing import Iterable


def normalize_drug_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def expand_drug_dict_items(items: Iterable) -> list[dict[str, str]]:
    expanded: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, str):
            expanded.append({"drug_name": item.strip()})
            continue
        if not isinstance(item, dict):
            expanded.append(item)
            continue

        names: list[str] = []
        primary = item.get("drug_name")
        if isinstance(primary, str) and primary.strip():
            names.append(primary.strip())

        for key, value in item.items():
            if key == "drug_name":
                continue
            if isinstance(key, str) and key.startswith("drug_name") and isinstance(value, str) and value.strip():
                names.append(value.strip())
            elif key in {"name", "drugName"} and isinstance(value, str) and value.strip():
                names.append(value.strip())

        if not names:
            expanded.append(item)
            continue

        seen: set[str] = set()
        for name in names:
            dedupe_key = normalize_drug_name(name)
            if dedupe_key and dedupe_key not in seen:
                seen.add(dedupe_key)
                expanded.append({"drug_name": name})
    return expanded
