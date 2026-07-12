"""Service layer for lab result interpretation."""
import ast
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.ai.client import AIClient
from app.core.config import settings
from app.models.schemas import LabInterpretationRequest, LabInterpretationResponse, LabInterpretation

logger = logging.getLogger(__name__)

DEFAULT_DISCLAIMER = "This output is interpretation support and not a diagnosis."
VALID_SEVERITIES = {"low", "moderate", "high", "critical"}
VALID_DIRECTIONS = {"rising", "falling", "stable"}
NORMALCY_CLAIM_PATTERN = re.compile(
    r"\b(within (the )?(normal |reference )?range|within (normal )?limits|"
    r"normal (range|level|result|value)s?|unremarkable|reassuring|"
    r"no(t)? (a )?concern(ing)?|nothing concerning)\b",
    re.IGNORECASE,
)
NORMAL_FLAG_KEYWORDS = ("normal", "in_range", "within_range", "within_limits")


class LabInterpreterService:
    """Service for handling lab result interpretation requests."""

    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()

    def process_request(self, request: LabInterpretationRequest) -> LabInterpretationResponse:
        """
        Process a lab interpretation request.

        Args:
            request: Lab interpretation request with lab results and optional context

        Returns:
            Lab interpretation response with structured interpretation
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing lab interpretation request {request_id}")

            patient_context_dict: Optional[Dict[str, Any]] = None
            if request.patient_context:
                patient_context_dict = request.patient_context.model_dump()

            lab_results_dict = [r.model_dump() for r in request.lab_results]
            historical_dict = [r.model_dump() for r in request.historical_lab_results]

            logger.info(
                f"Lab data: {len(lab_results_dict)} current, "
                f"{len(historical_dict)} historical"
            )

            interpretation_dict = self.ai_client.interpret_labs(
                patient_context=patient_context_dict,
                lab_results=lab_results_dict,
                historical_lab_results=historical_dict,
            )

            normalized_interpretation = self._normalize_interpretation(
                interpretation_dict=interpretation_dict,
                lab_results=lab_results_dict,
                historical_lab_results=historical_dict,
            )
            interpretation = LabInterpretation(**normalized_interpretation)

            response = LabInterpretationResponse(
                request_id=request_id,
                interpretation=interpretation,
                summary="Lab interpretation generated successfully.",
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "lab_result_count": len(request.lab_results),
                    "trend_count": len(interpretation.trends),
                    "provider": "openai",
                    "api_version": "v1",
                },
            )

            logger.info(f"Lab interpretation completed for request {request_id}")
            return response

        except ValueError as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing request {request.request_id}: {e}")
            raise ValueError(f"Lab interpretation failed: {str(e)}")

    def _normalize_interpretation(
        self,
        interpretation_dict: Dict[str, Any],
        lab_results: List[Dict[str, Any]],
        historical_lab_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Normalize AI output and reconstruct missing raw fields from input lab data."""
        current_records = self._prepare_records(lab_results)
        historical_records = self._prepare_records(historical_lab_results)
        all_records = historical_records + current_records

        return {
            "severity": self._normalize_severity(interpretation_dict.get("severity")),
            "key_findings": self._normalize_key_findings(
                interpretation_dict.get("key_findings", []),
                current_records=current_records,
                all_records=all_records,
            ),
            "patterns": self._normalize_patterns(interpretation_dict.get("patterns", [])),
            "trends": self._normalize_trends(
                interpretation_dict.get("trends", []),
                current_records=current_records,
                historical_records=historical_records,
            ),
            "follow_up_considerations": self._normalize_follow_up(
                interpretation_dict.get("follow_up_considerations", [])
            ),
            "disclaimer": self._normalize_disclaimer(interpretation_dict.get("disclaimer")),
        }

    def _normalize_severity(self, severity: Any) -> str:
        text = self._coerce_text(severity)
        if not text:
            return "moderate"
        lowered = text.lower()
        return lowered if lowered in VALID_SEVERITIES else text

    def _normalize_patterns(self, patterns: Any) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        if not isinstance(patterns, list):
            return normalized

        for pattern in patterns:
            if not isinstance(pattern, dict):
                continue

            label = self._coerce_text(pattern.get("label")) or "unknown_pattern"
            reason = self._soften_statement(self._coerce_text(pattern.get("reason")))
            if not reason:
                continue

            normalized.append({"label": label, "reason": reason})

        return normalized

    def _normalize_key_findings(
        self,
        findings: Any,
        current_records: List[Dict[str, Any]],
        all_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Optional[str]]]:
        normalized: List[Dict[str, Optional[str]]] = []
        if not isinstance(findings, list):
            findings = [findings] if findings else []

        for raw_finding in findings:
            candidate = self._parse_candidate(raw_finding)
            finding_text = ""
            lab_name = None
            if isinstance(candidate, dict):
                finding_text = self._coerce_text(
                    candidate.get("finding")
                    or candidate.get("text")
                    or candidate.get("summary")
                )
                lab_name = self._coerce_text(candidate.get("lab_name") or candidate.get("name"))
            elif isinstance(candidate, str):
                finding_text = candidate

            candidate_timestamp = (
                self._coerce_text(candidate.get("timestamp")) if isinstance(candidate, dict) else None
            )
            match = self._find_best_lab_match(
                lab_name, finding_text, current_records, all_records, timestamp_hint=candidate_timestamp
            )
            if not match and not lab_name:
                continue

            finding_text = self._soften_statement(finding_text)
            if not finding_text and match:
                finding_text = self._build_finding_text(match)

            resolved_lab_name = lab_name or (match or {}).get("name")
            resolved_value = self._first_non_empty(
                self._coerce_text(candidate.get("value")) if isinstance(candidate, dict) else None,
                (match or {}).get("value"),
            )
            resolved_unit = self._first_non_empty(
                self._coerce_text(candidate.get("unit")) if isinstance(candidate, dict) else None,
                (match or {}).get("unit"),
            )
            resolved_reference_range = self._first_non_empty(
                self._coerce_text(candidate.get("reference_range")) if isinstance(candidate, dict) else None,
                (match or {}).get("reference_range"),
            )
            resolved_flag = self._first_non_empty(
                self._coerce_text(candidate.get("flag")) if isinstance(candidate, dict) else None,
                (match or {}).get("flag"),
            )
            resolved_timestamp = self._first_non_empty(
                self._coerce_text(candidate.get("timestamp")) if isinstance(candidate, dict) else None,
                (match or {}).get("timestamp"),
            )

            # Guard against the model writing a finding sentence that cites a
            # different timestamped record of the same lab (e.g. two CBC1
            # entries where the narrative text for both mentions only one
            # of the two values). Structured fields are preserved as-is;
            # only the free-text sentence is rebuilt when it conflicts.
            if self._finding_text_cites_sibling_value(
                finding_text, resolved_lab_name, resolved_value, current_records, all_records
            ):
                finding_text = self._build_finding_text({
                    "name": resolved_lab_name,
                    "value": resolved_value,
                    "unit": resolved_unit,
                    "reference_range": resolved_reference_range,
                    "flag": resolved_flag,
                })

            # Guard against the model asserting a value is "within range" /
            # "normal" / "unremarkable" when the record has no reference
            # range to compare against and no resolved flag supporting that —
            # an unsupported reassurance is worse than no comment at all.
            resolved_record_for_check = {
                "reference_range": resolved_reference_range,
                "flag": resolved_flag,
            }
            checked_finding_text = self._strip_unsupported_normalcy_claim(
                finding_text, [resolved_record_for_check]
            )
            if checked_finding_text is None:
                finding_text = self._build_finding_text({
                    "name": resolved_lab_name,
                    "value": resolved_value,
                    "unit": resolved_unit,
                    "reference_range": resolved_reference_range,
                    "flag": resolved_flag,
                })
            else:
                finding_text = checked_finding_text

            normalized.append({
                "lab_name": resolved_lab_name,
                "value": resolved_value,
                "unit": resolved_unit,
                "reference_range": resolved_reference_range,
                "flag": resolved_flag,
                "timestamp": resolved_timestamp,
                "finding": finding_text,
            })

        return normalized

    def _normalize_trends(
        self,
        trends: Any,
        current_records: List[Dict[str, Any]],
        historical_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Optional[str]]]:
        normalized: List[Dict[str, Optional[str]]] = []
        if not isinstance(trends, list):
            return normalized

        all_records = historical_records + current_records
        for trend in trends:
            candidate = self._parse_candidate(trend)
            if not isinstance(candidate, dict):
                continue

            lab_name = self._coerce_text(candidate.get("lab_name") or candidate.get("name"))
            summary = self._soften_statement(self._coerce_text(candidate.get("summary")))
            if not lab_name:
                lab_name = self._extract_lab_name_from_text(summary, all_records)
            if not lab_name:
                continue

            series = self._records_for_lab(lab_name, all_records)
            ordered_series = self._order_records(series)
            from_record = ordered_series[0] if ordered_series else None
            to_record = ordered_series[-1] if ordered_series else None

            direction = self._normalize_direction(candidate.get("direction"), from_record, to_record)
            if not summary:
                summary = self._build_trend_summary(lab_name, direction, from_record, to_record)

            # If the model asserted the value is "within range" / "normal" /
            # "unremarkable" but the underlying records have no reference
            # range to compare against and no explicit normal flag, that
            # claim isn't grounded in the input data — rebuild deterministically.
            checked_summary = self._strip_unsupported_normalcy_claim(summary, [from_record, to_record])
            if checked_summary is None:
                summary = self._build_trend_summary(lab_name, direction, from_record, to_record)
            else:
                summary = checked_summary

            normalized.append({
                "lab_name": lab_name,
                "direction": direction,
                "summary": summary,
                "from_value": self._first_non_empty(
                    self._coerce_text(candidate.get("from_value")),
                    (from_record or {}).get("value"),
                ),
                "to_value": self._first_non_empty(
                    self._coerce_text(candidate.get("to_value")),
                    (to_record or {}).get("value"),
                ),
                "from_timestamp": self._first_non_empty(
                    self._coerce_text(candidate.get("from_timestamp")),
                    (from_record or {}).get("timestamp"),
                ),
                "to_timestamp": self._first_non_empty(
                    self._coerce_text(candidate.get("to_timestamp")),
                    (to_record or {}).get("timestamp"),
                ),
                "unit": self._first_non_empty(
                    self._coerce_text(candidate.get("unit")),
                    (to_record or {}).get("unit"),
                    (from_record or {}).get("unit"),
                ),
            })

        return normalized

    def _normalize_follow_up(self, considerations: Any) -> List[str]:
        if isinstance(considerations, str):
            considerations = [considerations]
        if not isinstance(considerations, list):
            return []

        normalized: List[str] = []
        for item in considerations:
            text = self._soften_follow_up(self._coerce_text(item))
            if text:
                normalized.append(text)
        return normalized

    def _normalize_disclaimer(self, disclaimer: Any) -> str:
        text = self._coerce_text(disclaimer)
        return text or DEFAULT_DISCLAIMER

    def _prepare_records(self, labs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for index, lab in enumerate(labs):
            records.append({
                "name": self._coerce_text(lab.get("name")),
                "value": self._coerce_text(lab.get("value")),
                "unit": self._coerce_text(lab.get("unit")),
                "reference_range": self._coerce_text(lab.get("reference_range")),
                "flag": self._coerce_text(lab.get("flag")),
                "timestamp": self._coerce_text(lab.get("timestamp")),
                "_index": index,
                "_parsed_timestamp": self._parse_timestamp(lab.get("timestamp")),
            })
        return records

    def _find_best_lab_match(
        self,
        lab_name: Optional[str],
        text: Optional[str],
        current_records: List[Dict[str, Any]],
        all_records: List[Dict[str, Any]],
        timestamp_hint: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_name = self._normalize_lab_name(lab_name)
        if normalized_name:
            current_matches = self._records_for_lab(normalized_name, current_records, by_normalized_name=True)
            if current_matches:
                return self._select_record(current_matches, timestamp_hint)

            all_matches = self._records_for_lab(normalized_name, all_records, by_normalized_name=True)
            if all_matches:
                return self._select_record(all_matches, timestamp_hint)

        extracted_name = self._extract_lab_name_from_text(text, current_records)
        if extracted_name:
            matches = self._records_for_lab(extracted_name, current_records)
            if matches:
                return self._select_record(matches, timestamp_hint)

        extracted_name = self._extract_lab_name_from_text(text, all_records)
        if extracted_name:
            matches = self._records_for_lab(extracted_name, all_records)
            if matches:
                return self._select_record(matches, timestamp_hint)

        return None

    def _select_record(
        self,
        records: List[Dict[str, Any]],
        timestamp_hint: Optional[str],
    ) -> Dict[str, Any]:
        """Pick a single record out of several same-named matches.

        If a usable timestamp hint is provided (e.g. the timestamp the model
        itself attached to this finding), prefer whichever candidate record is
        closest to it in time, since multiple lab results can share a name but
        differ by date. Otherwise fall back to the most recent record, which
        preserves prior behavior when no hint is available.
        """
        ordered = self._order_records(records)
        if len(ordered) == 1:
            return ordered[0]

        hint_dt = self._parse_timestamp(timestamp_hint)
        if hint_dt is not None:
            timestamped = [r for r in ordered if r.get("_parsed_timestamp") is not None]
            if timestamped:
                return min(
                    timestamped,
                    key=lambda r: abs((r["_parsed_timestamp"] - hint_dt).total_seconds()),
                )

        return ordered[-1]

    def _records_for_lab(
        self,
        lab_name: str,
        records: List[Dict[str, Any]],
        by_normalized_name: bool = False,
    ) -> List[Dict[str, Any]]:
        target = self._normalize_lab_name(lab_name)
        matched: List[Dict[str, Any]] = []
        for record in records:
            candidate_name = record.get("name")
            if not candidate_name:
                continue
            record_name = self._normalize_lab_name(candidate_name) if by_normalized_name else self._normalize_lab_name(candidate_name)
            if record_name == target:
                matched.append(record)
        return matched

    def _order_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not records:
            return []

        if all(record.get("_parsed_timestamp") is not None for record in records):
            return sorted(
                records,
                key=lambda record: (record["_parsed_timestamp"], record["_index"]),
            )

        return sorted(records, key=lambda record: record.get("_index", 0))

    def _normalize_direction(
        self,
        direction: Any,
        from_record: Optional[Dict[str, Any]],
        to_record: Optional[Dict[str, Any]],
    ) -> str:
        direction_text = self._coerce_text(direction)
        if direction_text and direction_text.lower() in VALID_DIRECTIONS:
            return direction_text.lower()

        from_value = self._to_float((from_record or {}).get("value"))
        to_value = self._to_float((to_record or {}).get("value"))
        if from_value is None or to_value is None:
            return "stable"
        if to_value > from_value:
            return "rising"
        if to_value < from_value:
            return "falling"
        return "stable"

    def _finding_text_cites_sibling_value(
        self,
        finding_text: Optional[str],
        lab_name: Optional[str],
        resolved_value: Optional[str],
        current_records: List[Dict[str, Any]],
        all_records: List[Dict[str, Any]],
    ) -> bool:
        """Detect when the model's free-text finding names a numeric value that
        belongs to a different timestamped record of the same lab, rather than
        the value actually attached to this finding."""
        if not finding_text or not lab_name or not resolved_value:
            return False

        resolved_num = self._to_float(resolved_value)
        if resolved_num is None:
            return False

        mentioned_numbers = {self._to_float(n) for n in re.findall(r"-?\d+\.?\d*", finding_text)}
        mentioned_numbers.discard(None)
        if not mentioned_numbers or resolved_num in mentioned_numbers:
            return False

        normalized_target = self._normalize_lab_name(lab_name)
        sibling_values = {
            self._to_float(record.get("value"))
            for record in current_records + all_records
            if self._normalize_lab_name(record.get("name")) == normalized_target
        }
        sibling_values.discard(None)
        sibling_values.discard(resolved_num)

        return bool(mentioned_numbers & sibling_values)

    def _has_reference_range(self, record: Optional[Dict[str, Any]]) -> bool:
        if not record:
            return False
        text = record.get("reference_range")
        return bool(text and str(text).strip())

    def _flag_indicates_normal(self, record: Optional[Dict[str, Any]]) -> bool:
        if not record:
            return False
        flag = (record.get("flag") or "").strip().lower()
        if not flag or flag in ("unknown", "n/a", "none"):
            return False
        return any(keyword in flag for keyword in NORMAL_FLAG_KEYWORDS)

    def _normalcy_claim_is_supported(self, records: List[Optional[Dict[str, Any]]]) -> bool:
        """A 'within range' / 'normal' claim is only supportable when at least
        one underlying record actually has a reference range to compare
        against, or an explicit normal-type flag. A blank reference_range and
        an unresolved flag (e.g. "unknown") give no basis for that claim."""
        return any(
            self._has_reference_range(record) or self._flag_indicates_normal(record)
            for record in records
            if record
        )

    def _strip_unsupported_normalcy_claim(
        self,
        text: Optional[str],
        records: List[Optional[Dict[str, Any]]],
    ) -> Optional[str]:
        """Return None if `text` asserts normalcy ("within range", "normal",
        "unremarkable", etc.) that the underlying records don't actually
        support, signaling the caller to rebuild the text deterministically.
        Returns `text` unchanged otherwise."""
        if not text or not NORMALCY_CLAIM_PATTERN.search(text):
            return text
        if self._normalcy_claim_is_supported(records):
            return text
        return None

    def _build_finding_text(self, record: Dict[str, Any]) -> str:
        name = record.get("name") or "This lab"
        flag = (record.get("flag") or "").lower()
        reference_range = record.get("reference_range")
        if flag == "high" and reference_range:
            return f"{name} is elevated above the reference range."
        if flag == "low" and reference_range:
            return f"{name} is below the reference range."
        if flag == "critical":
            return f"{name} is flagged as critical."
        return f"{name} result is {record.get('value') or 'reported'}."

    def _build_trend_summary(
        self,
        lab_name: str,
        direction: str,
        from_record: Optional[Dict[str, Any]],
        to_record: Optional[Dict[str, Any]],
    ) -> str:
        from_value = (from_record or {}).get("value")
        to_value = (to_record or {}).get("value")
        unit = (to_record or {}).get("unit") or (from_record or {}).get("unit")
        unit_suffix = f" {unit}" if unit else ""
        if from_value and to_value and from_value != to_value:
            return f"{lab_name} is {direction} from {from_value} to {to_value}{unit_suffix}."
        return f"{lab_name} appears {direction} based on the available values."

    def _parse_candidate(self, candidate: Any) -> Any:
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str):
            stripped = candidate.strip()
            if not stripped:
                return None
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    parsed_json = ast.literal_eval(stripped)
                    if isinstance(parsed_json, dict):
                        return parsed_json
                except (SyntaxError, ValueError):
                    pass
            return stripped
        return self._coerce_text(candidate)

    def _extract_lab_name_from_text(
        self,
        text: Optional[str],
        records: List[Dict[str, Any]],
    ) -> Optional[str]:
        if not text:
            return None

        lowered_text = text.lower()
        candidate_names = sorted(
            {record["name"] for record in records if record.get("name")},
            key=len,
            reverse=True,
        )
        for name in candidate_names:
            if name.lower() in lowered_text:
                return name
        return None

    def _soften_statement(self, text: Optional[str]) -> str:
        statement = self._coerce_text(text)
        if not statement:
            return ""

        replacements = [
            (r"\bconfirms?\b", "may suggest"),
            (r"\bconfirmed\b", "compatible with"),
            (r"\bdiagnostic of\b", "compatible with"),
            (r"\bindicates?\b", "may suggest"),
            (r"\bdemonstrates?\b", "may suggest"),
            (r"\bproves?\b", "may suggest"),
            (r"\bsuggests\b", "may suggest"),
            (r"\bconsistent with\b", "compatible with"),
            (r"\bdue to\b", "possibly related to"),
            (r"\bcaused by\b", "possibly related to"),
        ]
        for pattern, replacement in replacements:
            statement = re.sub(pattern, replacement, statement, flags=re.IGNORECASE)

        return re.sub(r"\s+", " ", statement).strip()

    def _soften_follow_up(self, text: Optional[str]) -> str:
        statement = self._soften_statement(text)
        if not statement:
            return ""

        if re.match(r"(?i)^(start|give|treat|prescribe|diagnose)\b", statement):
            return f"Consider {statement[0].lower()}{statement[1:]}"
        return statement

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        text = self._coerce_text(value)
        if not text:
            return None

        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _normalize_lab_name(self, name: Optional[str]) -> str:
        if not name:
            return ""
        return re.sub(r"\s+", " ", str(name).strip().lower())

    def _first_non_empty(self, *values: Optional[str]) -> Optional[str]:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _coerce_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _to_float(self, value: Any) -> Optional[float]:
        text = self._coerce_text(value)
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None