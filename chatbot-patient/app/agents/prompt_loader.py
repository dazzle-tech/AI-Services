"""Load the patient agent's system prompts from Prompts_patient.md.

Same mechanism as the clinician bot's loader (H2 heading -> first fenced ```text block,
base preamble prepended, {{vars}} filled at call time), pointed at the patient prompt
file so the two agents can never accidentally share a prompt.
"""
import logging
import re
from pathlib import Path
from typing import Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

_AGENT_HEADINGS = {
    "router": "Orchestrator",
    "collect": "Data-collection",
    "present": "Presentation",
    "confirm": "Confirmation",
}


def _extract_blocks(md_text: str) -> Dict[str, str]:
    blocks: Dict[str, str] = {}
    for section in re.split(r"^##\s+", md_text, flags=re.M):
        lines = section.splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        match = re.search(r"```text\n(.*?)```", section, flags=re.S)
        if match:
            blocks[heading] = match.group(1).rstrip()
    return blocks


def _fill(text: str, variables: Dict[str, object]) -> str:
    def repl(match: "re.Match") -> str:
        key = match.group(1).strip()
        return str(variables[key]) if key in variables else match.group(0)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", repl, text)


class PromptLoader:
    def __init__(self, path: Path | None = None):
        self._path = path or settings.prompts_path
        self._blocks: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        if not self._path.exists():
            logger.error("Prompts_patient.md not found at %s; prompts will be empty "
                         "and the agent will behave unsafely", self._path)
            self._blocks = {}
            return
        self._blocks = _extract_blocks(self._path.read_text(encoding="utf-8"))
        logger.info("Loaded %d prompt block(s) from %s", len(self._blocks), self._path)

    def _find(self, needle: str) -> str:
        for heading, block in self._blocks.items():
            if needle.lower() in heading.lower():
                return block
        return ""

    @property
    def preamble(self) -> str:
        return self._find("Base preamble")

    @property
    def loaded(self) -> bool:
        return bool(self._blocks) and bool(self.preamble)

    def system(self, agent_id: str, **variables) -> str:
        """Filled prompt: base preamble + the agent's block."""
        block = self._find(_AGENT_HEADINGS.get(agent_id, agent_id))
        return _fill(f"{self.preamble}\n\n{block}".strip(), variables)


loader = PromptLoader()
