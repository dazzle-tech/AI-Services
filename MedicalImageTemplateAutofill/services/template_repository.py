"""
Loads radiology templates from disk into memory and provides lookups.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from models.schemas import Template, TemplateSummary

logger = logging.getLogger(__name__)


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
