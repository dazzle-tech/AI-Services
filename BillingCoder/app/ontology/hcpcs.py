"""HCPCS Level II lookup via the NLM Clinical Tables public API."""
import logging
from typing import Dict, Optional

from app.ontology.clinical_tables import ClinicalTablesClient

logger = logging.getLogger(__name__)


class HCPCSClient:
    """Thin wrapper around ClinicalTablesClient for HCPCS lookups."""

    def __init__(self):
        """Reuse the ClinicalTablesClient for hcpcs queries."""
        self._client = ClinicalTablesClient()

    def lookup(self, term: str) -> Optional[Dict[str, Optional[str]]]:
        """Return {'code': ..., 'display': ...} or None."""
        return self._client.lookup_hcpcs(term)
