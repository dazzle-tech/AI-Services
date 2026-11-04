"""Formatter for radiology_report / imaging_report documents."""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

from app.models.schemas import RadiologyReportData, RadiologyReportEntry, RadiologySeverity
from app.services.formatters.base import BaseDocumentFormatter

_NEXT_HEADING = re.compile(r"^[A-Za-z][A-Za-z /]{0,40}:\s*")
_SEVERITIES = {"NOTHING", "MILD_MINOR", "MODERATE", "SEVERE", "CRITICAL"}
_SEVERITY_SYNONYMS = {
    "nothing": "NOTHING",
    "none": "NOTHING",
    "normal": "NOTHING",
    "unremarkable": "NOTHING",
    "mild": "MILD_MINOR",
    "minor": "MILD_MINOR",
    "mild_minor": "MILD_MINOR",
    "moderate": "MODERATE",
    "severe": "SEVERE",
    "critical": "CRITICAL",
}


class RadiologyReportFormatter(BaseDocumentFormatter):
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        reports_raw = extracted_fields.get("reports")
        sources: List[Dict[str, Any]]
        if isinstance(reports_raw, list):
            sources = [item for item in reports_raw if isinstance(item, dict)]
        else:
            sources = [extracted_fields]

        reports = [self._entry(item, raw_text) for item in sources]
        reports = [entry for entry in reports if self._has_content(entry)]
        data = RadiologyReportData(reports=reports)
        return data.model_dump(by_alias=True)

    def _entry(self, item: Dict[str, Any], raw_text: str) -> RadiologyReportEntry:
        severity = self._normalize_severity(self._first(item, "severity"))
        impression = self._labeled(raw_text, ("impression", "conclusion")) or self._first(item, "impression")
        critical_section = self._labeled(
            raw_text, ("critical findings", "critical finding", "critical result")
        )
        supplied = self._first(item, "criticalFindings", "critical_findings")
        chunks: List[str] = []
        if impression and (severity == "CRITICAL" or critical_section):
            chunks.append(impression)
        if critical_section:
            chunks.append(critical_section)
        if supplied:
            chunks.append(supplied)
        kept: List[str] = []
        for chunk in chunks:
            for sentence in re.split(r"(?<=[.!?])(?<!Dr\.)(?<!Mr\.)(?<!Ms\.)\s+|\n+", chunk):
                sentence = re.sub(r"^\d+\s*[\.\)\-]\s*", "", sentence).strip(" \t-*•")
                if not sentence or re.search(
                    r"\b(?:communicated|notified|by phone|via phone|telephoned)\b", sentence, re.IGNORECASE
                ):
                    continue
                folded = sentence.lower().rstrip(".")
                skip = False
                for index, existing in enumerate(kept):
                    existing_folded = existing.lower().rstrip(".")
                    if folded == existing_folded or folded in existing_folded:
                        skip = True
                        break
                    if existing_folded in folded:
                        kept[index] = sentence
                        skip = True
                        break
                if not skip:
                    kept.append(sentence)
        critical_findings = " ".join(kept) or None

        return RadiologyReportEntry(
            report_date=self._first(item, "reportDate", "report_date", "study_date"),
            test_name=self._test_name(item),
            report=self._report_html(item, raw_text),
            severity=severity,
            radiologist_information=self._first(
                item, "radiologistInformation", "radiologist_information", "radiologist"
            )
            or self._labeled(
                raw_text,
                ("reporting radiologist", "radiologist", "interpreted by", "read by"),
            ),
            critical_findings=critical_findings,
            radiologist_comments=self._first(
                item, "radiologistComments", "radiologist_comments", "recommendation", "recommendations"
            )
            or self._labeled(
                raw_text,
                (
                    "radiologist comments",
                    "radiologist comment",
                    "recommendation",
                    "recommendations",
                    "advice",
                    "comments",
                    "comment",
                ),
            ),
            physician_name=self._first(
                item, "physicianName", "physician_name", "ordering_provider", "referring_physician"
            )
            or self._labeled(
                raw_text,
                (
                    "referring physician",
                    "ordering physician",
                    "ordering provider",
                    "requesting physician",
                ),
            ),
        )

    @staticmethod
    def _labeled(text: str, labels: tuple[str, ...]) -> Optional[str]:
        if not text:
            return None
        label_pattern = re.compile(
            rf"^({'|'.join(re.escape(label) for label in labels)})\s*:\s*(.*)$",
            re.IGNORECASE,
        )
        lines = text.splitlines()
        for index, line in enumerate(lines):
            match = label_pattern.match(line.strip())
            if not match:
                continue
            parts = [match.group(2).strip()] if match.group(2).strip() else []
            for follow in lines[index + 1:]:
                stripped = follow.strip()
                if not stripped:
                    if parts:
                        break
                    continue
                if _NEXT_HEADING.match(stripped):
                    break
                parts.append(stripped)
            if parts:
                return " ".join(parts)
        return None

    def _test_name(self, item: Dict[str, Any]) -> Optional[str]:
        explicit = self._first(item, "testName", "test_name")
        if explicit:
            return explicit
        modality = self._first(item, "modality")
        body_part = self._first(item, "body_part_examined", "bodyPartExamined")
        parts = [part for part in (modality, body_part) if part]
        return " ".join(parts) or None

    def _report_html(self, item: Dict[str, Any], raw_text: str) -> Optional[str]:
        """Clinical narrative that has no field of its own. Names, recommendation, and critical findings stay in their fields."""
        sections = (
            ("Clinical History", ("clinical history", "clinical indication", "indication"), None),
            ("Technique", ("technique",), None),
            ("Comparison", ("comparison", "comparisons"), None),
            ("Findings", ("findings",), "findings"),
            ("Impression", ("impression", "conclusion"), "impression"),
        )
        fallbacks = {
            "findings": ("findings",),
            "impression": ("impression",),
        }
        paragraphs: List[str] = []
        for title, labels, field_name in sections:
            text = self._labeled(raw_text, labels)
            if text is None and field_name:
                text = self._first(item, *fallbacks[field_name])
            if text:
                paragraphs.append(f"<p><strong>{title}:</strong> {html.escape(text)}</p>")
        if paragraphs:
            return "".join(paragraphs)
        supplied = self._first(item, "report")
        if supplied and "<p>" in supplied:
            return supplied
        if supplied:
            return f"<p>{html.escape(supplied)}</p>"
        return None

    def _normalize_severity(self, severity: Optional[str]) -> Optional[RadiologySeverity]:
        if not severity:
            return None
        token = severity.strip().upper().replace(" ", "_").replace("-", "_")
        if token in _SEVERITIES:
            return token  # type: ignore[return-value]
        mapped = _SEVERITY_SYNONYMS.get(severity.strip().lower().replace(" ", "_").replace("-", "_"))
        return mapped  # type: ignore[return-value]

    @staticmethod
    def _has_content(entry: RadiologyReportEntry) -> bool:
        return any(
            (
                entry.report_date,
                entry.test_name,
                entry.report,
                entry.severity,
                entry.radiologist_information,
                entry.critical_findings,
                entry.radiologist_comments,
                entry.physician_name,
            )
        )
