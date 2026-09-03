"""Field-level mapping from stage-1 JSON onto ViewDecoders."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.ai.client import AIClient
from app.ai.mapping_prompts import build_system_prompt, build_user_prompt
from app.core.config import settings
from app.models.schemas import DecoderField, ReshapeResponse, ViewDecoder, ViewResult

logger = logging.getLogger(__name__)

MISSING = object()
NON_DIRECT = {"summarize", "concat", "split", "extract"}


class AllRequiredFieldsFailed(Exception):
    """Raised when every required decoder field fails to resolve (single-view helper)."""

    def __init__(self, view_id: str, warnings: list[str]) -> None:
        self.view_id = view_id
        self.warnings = warnings
        super().__init__(f"All required fields failed for view {view_id}")


class AllViewsFailed(Exception):
    """Raised when none of the requested views could be resolved."""

    def __init__(self, results: list[ViewResult]) -> None:
        self.results = results
        super().__init__("None of the requested views could be resolved")


@dataclass
class _ViewWork:
    decoder: ViewDecoder
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    required_total: int = 0
    required_failed: int = 0
    found: bool = True

    @property
    def succeeded(self) -> bool:
        if not self.found:
            return False
        if self.required_total > 0 and self.required_failed == self.required_total:
            return False
        return True

    def to_result(self) -> ViewResult:
        return ViewResult(view_id=self.decoder.view_id, data=self.data, warnings=self.warnings)


@dataclass
class _LlmJob:
    key: str
    work: _ViewWork
    field: DecoderField
    source: Any


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
    if isinstance(current, list) and token.isdigit():
        index = int(token)
        if 0 <= index < len(current):
            return _walk(current[index], rest)
        return MISSING
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


def _mark_missing(work: _ViewWork, field: DecoderField, message: str) -> None:
    work.data[field.field_name] = None
    label = "Required" if field.required else "Optional"
    work.warnings.append(f"{label} field '{field.field_name}' {message}")
    if field.required:
        work.required_failed += 1


def _collect_fields(work: _ViewWork, stage1_output: dict[str, Any], llm_jobs: list[_LlmJob]) -> None:
    for field in work.decoder.fields:
        if field.required:
            work.required_total += 1
        source = resolve_path(stage1_output, field.source_path)
        if is_empty(source):
            _mark_missing(
                work,
                field,
                f"could not be resolved from source_path '{field.source_path}'",
            )
            continue
        if field.transform == "direct" or field.transform not in NON_DIRECT:
            work.data[field.field_name] = coerce_value(source, field.field_type)
        else:
            llm_jobs.append(
                _LlmJob(
                    key=f"{work.decoder.view_id}::{field.field_name}",
                    work=work,
                    field=field,
                    source=source,
                )
            )


def reshape(
    stage1_output: dict[str, Any],
    view_decoder: ViewDecoder,
    *,
    context: str,
    purpose: str,
    client: AIClient | None = None,
) -> ViewResult:
    """Map one decoder. Raises AllRequiredFieldsFailed if that view fully fails."""
    response = reshape_many(
        stage1_output,
        [view_decoder],
        context=context,
        purpose=purpose,
        client=client,
        raise_if_all_failed=False,
    )
    result = response.results[0]
    required_names = {f.field_name for f in view_decoder.fields if f.required}
    required_failed = sum(1 for name in required_names if is_empty(result.data.get(name, MISSING)))
    if required_names and required_failed == len(required_names):
        raise AllRequiredFieldsFailed(view_decoder.view_id, result.warnings)
    return result


def reshape_many(
    stage1_output: dict[str, Any],
    view_decoders: list[ViewDecoder],
    *,
    context: str,
    purpose: str,
    client: AIClient | None = None,
    unresolved: list[ViewResult] | None = None,
    raise_if_all_failed: bool = True,
) -> ReshapeResponse:
    """Map many decoders. One LLM round-trip for all non-direct fields across views."""
    works = [_ViewWork(decoder=decoder) for decoder in view_decoders]
    llm_jobs: list[_LlmJob] = []
    for work in works:
        _collect_fields(work, stage1_output, llm_jobs)

    if llm_jobs:
        mapped = _map_llm_fields(llm_jobs, context=context, purpose=purpose, client=client)
        for job in llm_jobs:
            value = mapped.get(job.key, mapped.get(job.field.field_name, MISSING))
            if is_empty(value):
                _mark_missing(
                    job.work,
                    job.field,
                    f"LLM transform '{job.field.transform}' returned an empty result",
                )
            else:
                job.work.data[job.field.field_name] = coerce_value(value, job.field.field_type)

    results = [work.to_result() for work in works]
    if unresolved:
        results.extend(unresolved)

    any_success = any(work.succeeded for work in works)
    if raise_if_all_failed and not any_success:
        raise AllViewsFailed(results)

    logger.info(
        "Reshape batch complete views=%s",
        len(results),
        extra={"event_type": "reshape"},
    )
    return ReshapeResponse(results=results)


def _map_llm_fields(
    jobs: list[_LlmJob],
    *,
    context: str,
    purpose: str,
    client: AIClient | None,
) -> dict[str, Any]:
    pairs = [(job.field, job.source) for job in jobs]
    keys = [job.key for job in jobs]

    if client is None and settings.use_llm_stub:
        return {job.key: _stub_transform(job.field, job.source) for job in jobs}

    llm = client or AIClient()
    payload = llm.complete_json(
        model=settings.mapping_model,
        system_prompt=build_system_prompt(context=context, purpose=purpose),
        user_prompt=build_user_prompt(
            context=context,
            purpose=purpose,
            fields=pairs,
            json_keys=keys,
        ),
    )
    if not isinstance(payload, dict):
        return {}
    return payload
