"""Field-level mapping from stage-1 JSON onto a ViewDecoder."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.ai.client import AIClient
from app.ai.mapping_prompts import build_system_prompt, build_user_prompt
from app.core.config import settings
from app.models.schemas import DecoderField, ReshapeResponse, ViewDecoder

logger = logging.getLogger(__name__)

MISSING = object()


class AllRequiredFieldsFailed(Exception):
    """Raised when every required decoder field fails to resolve."""

    def __init__(self, view_id: str, warnings: list[str]) -> None:
        self.view_id = view_id
        self.warnings = warnings
        super().__init__(f"All required fields failed for view {view_id}")


def tokenize_path(path: str) -> list[str]:
    """Split a source_path into tokens. Supports dotted keys and `[*]`."""
    tokens: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(path):
        if path.startswith("[*]", i):
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append("[*]")
            i += 3
        elif path[i] == ".":
            if buf:
                tokens.append("".join(buf))
                buf = []
            i += 1
        else:
            buf.append(path[i])
            i += 1
    if buf:
        tokens.append("".join(buf))
    return [t for t in tokens if t]


def resolve_path(data: Any, path: str) -> Any:
    """Resolve a simple JSON path with dot notation and `[*]` list flattening."""
    if not path or not path.strip():
        return MISSING
    return _walk(data, tokenize_path(path.strip()))


def _walk(current: Any, tokens: list[str]) -> Any:
    if not tokens:
        return current
    token, rest = tokens[0], tokens[1:]
    if token == "[*]":
        if not isinstance(current, list):
            return MISSING
        collected: list[Any] = []
        for item in current:
            value = _walk(item, rest)
            if value is MISSING:
                continue
            if isinstance(value, list) and "[*]" in rest:
                collected.extend(value)
            else:
                collected.append(value)
        return collected
    if isinstance(current, dict) and token in current:
        return _walk(current[token], rest)
    return MISSING


def is_empty(value: Any) -> bool:
    if value is MISSING or value is None:
        return True
    if value == "" or value == [] or value == {}:
        return True
    return False


def coerce_value(value: Any, field_type: str) -> Any:
    if value is MISSING or value is None:
        return None
    if field_type == "string":
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)
    if field_type == "list":
        if isinstance(value, list):
            return value
        return [value]
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return bool(value)
    if field_type == "object":
        if isinstance(value, dict):
            return value
        return {"value": value}
    if field_type == "date":
        return str(value)
    return value


def _stub_transform(field: DecoderField, source_slice: Any) -> Any:
    hint = field.transform_hint
    if field.transform == "concat":
        sep = hint if hint is not None else " "
        if isinstance(source_slice, list):
            return sep.join(str(item) for item in source_slice)
        return str(source_slice)
    if field.transform == "split":
        sep = hint if hint is not None else ","
        return [part.strip() for part in str(source_slice).split(sep)]
    if field.transform == "extract":
        return source_slice
    if field.transform == "summarize":
        text = source_slice if isinstance(source_slice, str) else json.dumps(source_slice)
        return text[:500]
    return source_slice


def reshape(
    stage1_output: dict[str, Any],
    view_decoder: ViewDecoder,
    *,
    context: str,
    purpose: str,
    client: AIClient | None = None,
) -> ReshapeResponse:
    data: dict[str, Any] = {}
    warnings: list[str] = []
    required_total = 0
    required_failed = 0
    llm_jobs: list[tuple[DecoderField, Any]] = []

    for field in view_decoder.fields:
        if field.required:
            required_total += 1
        source = resolve_path(stage1_output, field.source_path)
        if is_empty(source):
            data[field.field_name] = None
            label = "Required" if field.required else "Optional"
            warnings.append(
                f"{label} field '{field.field_name}' could not be resolved from "
                f"source_path '{field.source_path}'"
            )
            if field.required:
                required_failed += 1
            continue
        if field.transform == "direct":
            data[field.field_name] = coerce_value(source, field.field_type)
        else:
            llm_jobs.append((field, source))

    if llm_jobs:
        mapped = _map_llm_fields(llm_jobs, context=context, purpose=purpose, client=client)
        for field, _ in llm_jobs:
            value = mapped.get(field.field_name, MISSING)
            if is_empty(value):
                data[field.field_name] = None
                label = "Required" if field.required else "Optional"
                warnings.append(
                    f"{label} field '{field.field_name}' LLM transform '{field.transform}' "
                    "returned an empty result"
                )
                if field.required:
                    required_failed += 1
            else:
                data[field.field_name] = coerce_value(value, field.field_type)

    if required_total > 0 and required_failed == required_total:
        raise AllRequiredFieldsFailed(view_decoder.view_id, warnings)

    logger.info(
        "Reshape complete fields=%s warnings=%s",
        len(view_decoder.fields),
        len(warnings),
        extra={"view_id": view_decoder.view_id, "event_type": "reshape"},
    )
    return ReshapeResponse(view_id=view_decoder.view_id, data=data, warnings=warnings)


def _map_llm_fields(
    jobs: list[tuple[DecoderField, Any]],
    *,
    context: str,
    purpose: str,
    client: AIClient | None,
) -> dict[str, Any]:
    if client is None and settings.use_llm_stub:
        return {field.field_name: _stub_transform(field, source) for field, source in jobs}

    llm = client or AIClient()
    payload = llm.complete_json(
        model=settings.mapping_model,
        system_prompt=build_system_prompt(context=context, purpose=purpose),
        user_prompt=build_user_prompt(context=context, purpose=purpose, fields=jobs),
    )
    if not isinstance(payload, dict):
        return {}
    return payload
