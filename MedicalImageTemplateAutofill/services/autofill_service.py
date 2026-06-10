"""
Autofill service that maps raw input into a template's fields and returns
the final radiology report inside TEMPLATE_TEXT.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models.schemas import AutofillResponse, FieldValidation, Template
from services.template_repository import TemplateRepository

logger = logging.getLogger(__name__)

_REPORT_SIGNATURES = {
    "el": "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ\n\nΜΙΧΑΛΗΣ ΚΕΛΟΓΡΗΓΟΡΗΣ\n(κωδικός ΓΕΣΥ: D2022)",
    "en": "REPORTING RADIOLOGIST\n\nMICHALIS KELOGRIGORIS\n(GESY code: D2022)",
    "ar": "اختصاصي الأشعة\n\nميخاليس كيلوجريجوريس\n(رمز GESY: D2022)",
}

_SECTION_LABELS = {
    "el": {
        "clinical_history": "ΚΛΙΝΙΚΟ ΙΣΤΟΡΙΚΟ",
        "technique": "ΤΕΧΝΙΚΗ",
        "comparison": "ΣΥΓΚΡΙΣΗ",
        "findings": "ΕΥΡΗΜΑΤΑ",
        "impression": "ΣΥΜΠΕΡΑΣΜΑ",
        "not_addressed": "Δεν αναφέρεται.",
        "technique_default": "Η εξέταση πραγματοποιήθηκε με τυπικό πρωτόκολλο.",
        "comparison_default": "Δεν υπάρχει διαθέσιμη συγκριτική εξέταση.",
        "history_default": "Δεν δόθηκαν επαρκή κλινικά στοιχεία.",
        "impression_default": "Αναμένεται ολοκλήρωση από τον ακτινολόγο.",
    },
    "en": {
        "clinical_history": "CLINICAL HISTORY",
        "technique": "TECHNIQUE",
        "comparison": "COMPARISON",
        "findings": "FINDINGS",
        "impression": "IMPRESSION",
        "not_addressed": "Not addressed.",
        "technique_default": "The examination was performed using the standard protocol.",
        "comparison_default": "No prior study is available for comparison.",
        "history_default": "Insufficient clinical history was provided.",
        "impression_default": "Pending radiologist completion.",
    },
    "ar": {
        "clinical_history": "التاريخ السريري",
        "technique": "الطريقة",
        "comparison": "المقارنة",
        "findings": "النتائج",
        "impression": "الانطباع",
        "not_addressed": "غير مذكور.",
        "technique_default": "أُجري الفحص وفق البروتوكول القياسي.",
        "comparison_default": "لا توجد دراسة سابقة للمقارنة.",
        "history_default": "لم تُقدَّم معطيات سريرية كافية.",
        "impression_default": "بانتظار استكمال اختصاصي الأشعة.",
    },
}

_GREEK_FINDING_PREFIXES = {
    "findings_gallbladder": "Χοληδόχος κύστη",
    "findings_bile_ducts": "Χοληφόρα",
    "findings_liver": "Ήπαρ",
    "findings_pulmonary_arteries": "Πνευμονικές αρτηρίες",
    "findings_heart": "Καρδιά και μεγάλα αγγεία",
    "findings_lungs": "Πνευμονικά παρεγχύματα και αεραγωγοί",
    "findings_pleura": "Υπεζωκότες",
    "findings_mediastinum": "Μεσοθωράκιο και λεμφαδένες",
}


def _build_system_prompt(output_language: str) -> str:
    return (
        "You are an experienced radiologist's reporting assistant.\n"
        "Given a raw clinician dictation or clinical input and a radiology report template,\n"
        "populate each template field with concise, clinically appropriate text derived\n"
        "strictly from the input. Do not invent findings. If the input does not address a\n"
        "field, return an empty string for that field.\n\n"
        f"The requested output language is '{output_language}'.\n"
        "If the language is 'el', write the field values in Greek.\n"
        "If the language is 'en', write the field values in English.\n"
        "If the language is 'ar', write the field values in Arabic.\n"
        "Keep JSON keys exactly as provided.\n\n"
        "Return ONLY a JSON object that maps each template field's `name` to a string\n"
        "value. No commentary, no markdown code fences."
    )


class AutofillService:
    def __init__(
        self,
        repository: TemplateRepository,
        openai_api_key: Optional[str],
        model: str,
        temperature: float,
        mock_llm: bool = False,
    ):
        self.repository = repository
        self.openai_api_key = openai_api_key
        self.model = model
        self.temperature = temperature
        self.mock_llm = mock_llm
        self._client = None
        self.initialized = False

    def initialize(self) -> None:
        if self.initialized:
            return
        if self.mock_llm:
            logger.warning("Autofill running in MOCK_LLM mode - no OpenAI calls will be made")
            self.initialized = True
            return
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY missing - autofill will fall back to deterministic output")
            self.initialized = True
            return

        from openai import OpenAI

        self._client = OpenAI(api_key=self.openai_api_key)
        self.initialized = True
        logger.info("Autofill service initialized with model %s", self.model)

    async def autofill(
        self,
        template: Template,
        input_data: str,
        request_id: Optional[str] = None,
        patient_context: Optional[dict[str, Any]] = None,
        output_language: str = "el",
    ) -> AutofillResponse:
        if not self.initialized:
            self.initialize()

        if self.mock_llm or self._client is None:
            populated = self._mock_populate(template, input_data, output_language)
            confidence = 0.4
        else:
            populated = await self._llm_populate(template, input_data, patient_context, output_language)
            confidence = 0.85

        missing_required = [
            f.name for f in template.fields if f.required and not populated.get(f.name)
        ]
        warnings = [
            FieldValidation(
                field_name=name,
                issue="Required field is empty - input did not contain enough information.",
                severity="warning",
            )
            for name in missing_required
        ]
        if warnings:
            logger.info("Autofill produced %d internal warning(s) for %s", len(warnings), template.template_id)
        if missing_required:
            confidence = max(0.0, confidence - 0.1 * len(missing_required))

        template_name = self.repository.get_localized_template_name(template, output_language)
        rendered = self._render(template, template_name, populated, output_language)

        return AutofillResponse(
            ID=0,
            TEMPLATE_NAME=template_name,
            TEMPLATE_TEXT=rendered,
            STATUS_ID=None,
            CREATED_BY="autofill-service",
            CREATION_DATETIME=datetime.utcnow(),
            DELETED_BY=None,
            DELETE_DATETIME=None,
            UPDATED_BY="autofill-service",
            UPDATE_DATETIME=datetime.utcnow(),
            Physician=self._physician_name(output_language),
        )

    async def _llm_populate(
        self,
        template: Template,
        input_data: str,
        patient_context: Optional[dict[str, Any]],
        output_language: str,
    ) -> dict[str, Any]:
        field_spec = [
            {
                "name": f.name,
                "label": f.label,
                "description": f.description,
                "required": f.required,
            }
            for f in template.fields
        ]
        user_payload = {
            "template": {
                "template_id": template.template_id,
                "name": template.name,
                "modality": template.modality,
                "body_region": template.body_region,
                "fields": field_spec,
            },
            "patient_context": patient_context or {},
            "input": input_data,
            "output_language": output_language,
        }

        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _build_system_prompt(output_language)},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON content: %s", content[:200])
            data = {}

        populated: dict[str, Any] = {}
        for field in template.fields:
            value = data.get(field.name, "")
            if isinstance(value, list):
                value = "\n".join(str(v) for v in value)
            populated[field.name] = "" if value is None else str(value)
        return populated

    @staticmethod
    def _mock_populate(template: Template, input_data: str, output_language: str) -> dict[str, Any]:
        """Deterministic placeholder content used when a live LLM is unavailable."""
        snippet = input_data.strip().replace("\n", " ")
        snippet = (snippet[:140] + "...") if len(snippet) > 140 else snippet
        labels = _SECTION_LABELS.get(output_language, _SECTION_LABELS["el"])

        if template.template_id == "us_abdomen_ruq" and output_language == "el":
            return {
                "exam": "Υπερηχογράφημα άνω και κάτω κοιλίας.",
                "clinical_history": snippet or "Άλγος δεξιού υποχονδρίου.",
                "technique": "Διενεργήθηκε υπερηχογραφικός έλεγχος άνω και κάτω κοιλίας.",
                "comparison": "",
                "findings_gallbladder": "χωρίς ηχογενές ενδοαυλικό περιεχόμενο, με φυσιολογικό πάχος τοιχώματος.",
                "findings_bile_ducts": "Ένδο- έξωηπατικά χοληφόρα χωρίς διάταση.",
                "findings_liver": "φυσιολογικού μεγέθους και ηχοδομής, χωρίς εστιακές αλλοιώσεις.",
                "impression": "Δεν αναδεικνύονται παθολογικά υπερηχογραφικά ευρήματα από το ήπαρ, τη χοληδόχο κύστη και τα χοληφόρα.",
            }

        out: dict[str, Any] = {}
        for field in template.fields:
            if field.name == "exam":
                out[field.name] = ""
            elif field.name == "clinical_history":
                out[field.name] = snippet or labels["history_default"]
            elif field.name == "technique":
                if output_language == "el":
                    out[field.name] = f"Διενεργήθηκε εξέταση {template.modality} με τυπικό πρωτόκολλο."
                elif output_language == "ar":
                    out[field.name] = f"أُجري فحص {template.modality} وفق البروتوكول القياسي."
                else:
                    out[field.name] = f"Standard {template.modality} protocol."
            elif field.name == "comparison":
                out[field.name] = labels["comparison_default"]
            elif field.name == "impression":
                out[field.name] = labels["impression_default"]
            else:
                out[field.name] = ""
        return out

    @staticmethod
    def _physician_name(output_language: str) -> str:
        if output_language == "ar":
            return "ميخاليس كيلوجريجوريس"
        if output_language == "en":
            return "MICHALIS KELOGRIGORIS"
        return "ΜΙΧΑΛΗΣ ΚΕΛΟΓΡΗΓΟΡΗΣ"

    @staticmethod
    def _render(template: Template, template_name: str, populated: dict[str, Any], output_language: str) -> str:
        if output_language == "el" and template.template_id == "us_abdomen_ruq":
            liver = (populated.get("findings_liver") or "").strip()
            gallbladder = (populated.get("findings_gallbladder") or "").strip()
            bile_ducts = (populated.get("findings_bile_ducts") or "").strip()
            impression = (populated.get("impression") or "").strip()
            lines = [
                template_name,
                "",
                f"Ήπαρ {liver or 'φυσιολογικού μεγέθους και ηχοδομής, χωρίς εστιακές αλλοιώσεις.'}",
                f"Χοληδόχος κύστη {gallbladder or 'χωρίς ηχογενές ενδοαυλικό περιεχόμενο, με φυσιολογικό πάχος τοιχώματος.'}",
                bile_ducts or "Ένδο- έξωηπατικά χοληφόρα χωρίς διάταση.",
            ]
            if impression:
                lines.extend(["", impression])
            lines.extend(["", _REPORT_SIGNATURES["el"]])
            return "\n".join(lines).strip()

        labels = _SECTION_LABELS.get(output_language, _SECTION_LABELS["el"])
        findings_lines = []
        for field in template.fields:
            if not field.name.startswith("findings"):
                continue
            value = (populated.get(field.name) or "").strip()
            if not value:
                continue
            if output_language == "el":
                prefix = _GREEK_FINDING_PREFIXES.get(field.name, field.label)
                findings_lines.append(f"{prefix}: {value}")
            else:
                findings_lines.append(value)

        history = (populated.get("clinical_history") or "").strip() or labels["history_default"]
        technique = (populated.get("technique") or "").strip() or labels["technique_default"]
        comparison = (populated.get("comparison") or "").strip() or labels["comparison_default"]
        impression = (populated.get("impression") or "").strip() or labels["impression_default"]

        lines = [
            template_name,
            "",
            labels["clinical_history"],
            history,
            "",
            labels["technique"],
            technique,
            "",
            labels["comparison"],
            comparison,
            "",
            labels["findings"],
        ]
        if findings_lines:
            lines.extend(findings_lines)
        else:
            lines.append(labels["not_addressed"])
        lines.extend(
            [
                "",
                labels["impression"],
                impression,
                "",
                _REPORT_SIGNATURES.get(output_language, _REPORT_SIGNATURES["el"]),
            ]
        )
        return "\n".join(lines).strip()
