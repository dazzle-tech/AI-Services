"""
Loads radiology templates from disk into memory and provides lookups.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from models.schemas import Template, TemplateSummary

logger = logging.getLogger(__name__)

_LOCALIZED_TEMPLATE_NAMES = {
    "ct_chest": {
        "el": "ΑΞΟΝΙΚΗ ΤΟΜΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ - ΠΡΩΤΟΚΟΛΛΟ ΠΝΕΥΜΟΝΙΚΗΣ ΕΜΒΟΛΗΣ",
        "en": "CT CHEST - PULMONARY EMBOLISM PROTOCOL",
        "ar": "التصوير المقطعي للصدر - بروتوكول الانصمام الرئوي",
    },
    "mammography_screening": {
        "el": "ΜΑΣΤΟΓΡΑΦΙΑ ΠΡΟΛΗΠΤΙΚΟΥ ΕΛΕΓΧΟΥ",
        "en": "SCREENING MAMMOGRAPHY",
        "ar": "تصوير الثدي الشعاعي التحري",
    },
    "mri_brain": {
        "el": "ΜΑΓΝΗΤΙΚΗ ΤΟΜΟΓΡΑΦΙΑ ΕΓΚΕΦΑΛΟΥ",
        "en": "MRI BRAIN",
        "ar": "التصوير بالرنين المغناطيسي للدماغ",
    },
    "mri_lumbar_spine": {
        "el": "ΜΑΓΝΗΤΙΚΗ ΤΟΜΟΓΡΑΦΙΑ ΟΣΦΥΪΚΗΣ ΜΟΙΡΑΣ ΣΠΟΝΔΥΛΙΚΗΣ ΣΤΗΛΗΣ",
        "en": "MRI LUMBAR SPINE",
        "ar": "التصوير بالرنين المغناطيسي للعمود الفقري القطني",
    },
    "us_abdomen_ruq": {
        "el": "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ",
        "pt": "Ecografia abdominal",
        "en": "ABDOMINAL ULTRASOUND",
        "ar": "التصوير بالأمواج فوق الصوتية للبطن",
    },
    "us_abdomen_pt": {
        "pt": "Ecografia abdominal",
        "el": "ΥΠΕΡΗΧΟΓΡΑΦΗΜΑ ΑΝΩ ΚΑΙ ΚΑΤΩ ΚΟΙΛΙΑΣ",
        "en": "ABDOMINAL ULTRASOUND",
        "ar": "التصوير بالأمواج فوق الصوتية للبطن",
    },
}


class TemplateRepository:
    def __init__(self, templates_dir: str):
        self.templates_dir = Path(templates_dir)
        self._templates: dict[str, Template] = {}

    def load(self) -> None:
        self._templates.clear()
        if not self.templates_dir.exists():
            logger.warning("Templates directory not found: %s", self.templates_dir)
            return

        for file_path in sorted(self.templates_dir.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                template = Template(**data)
                self._templates[template.template_id] = template
            except Exception as exc:
                logger.error("Failed to load template %s: %s", file_path.name, exc)

        logger.info("Loaded %d templates from %s", len(self._templates), self.templates_dir)

    def all(self) -> list[Template]:
        return list(self._templates.values())

    def summaries(self) -> list[TemplateSummary]:
        return [
            TemplateSummary(
                template_id=t.template_id,
                name=t.name,
                modality=t.modality,
                body_region=t.body_region,
                description=t.description,
            )
            for t in self._templates.values()
        ]

    def get(self, template_id: str) -> Optional[Template]:
        return self._templates.get(template_id)

    def exists(self, template_id: str) -> bool:
        return template_id in self._templates

    def get_localized_template_name(self, template: Template, output_language: str = "el") -> str:
        language = (output_language or "el").strip().lower()
        localized = _LOCALIZED_TEMPLATE_NAMES.get(template.template_id, {})
        return localized.get(language) or localized.get("en") or template.name

# Modality hard filter helper.
def filter_by_modality(templates, modality: str):
    mod = (modality or "").strip().upper()
    if not mod:
        return list(templates)
    allowed = {"CR", "DX"} if mod in {"CR", "DX"} else {mod}
    out = []
    for t in templates:
        tmod = t.get("modality") if isinstance(t, dict) else getattr(t, "modality", None)
        if (str(tmod or "").strip().upper()) in allowed:
            out.append(t)
    return out
