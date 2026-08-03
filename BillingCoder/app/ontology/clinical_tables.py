"""NLM Clinical Tables API client for ICD-10-CM and HCPCS lookups.

Public, keyless API (https://clinicaltables.nlm.nih.gov) -- unlike
BioPortal, no apikey is required. CPT (HCPCS Level I) is AMA copyrighted
and has no equivalent free public lookup API, so it is not covered here;
CPT grounding in this project is RAG/seed-only (see coding_seed_terms.json).
"""
import logging
from typing import Any, Dict, List, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class ClinicalTablesClient:
    """Thin REST client for the NLM Clinical Tables search API."""

    def __init__(self):
        """Capture base URL from settings."""
        self._base_url = settings.clinical_tables_base_url.rstrip("/")
        self._timeout = 15

    def _search(
        self, dataset: str, term: str, code_field: str, display_field: str, max_list: int = 1
    ) -> List[List[Any]]:
        """Run a Clinical Tables /search call against the given dataset.

        Response shape is a 4-element array:
        [total_count, code_list, extra_data, display_rows]. This returns
        display_rows, where each row is [code_field_value, display_field_value].
        """
        url = f"{self._base_url}/{dataset}/v3/search"
        params = {
            "terms": term,
            "sf": f"{code_field},{display_field}",
            "df": f"{code_field},{display_field}",
            "maxList": max_list,
        }
        try:
            response = requests.get(url, params=params, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Clinical Tables request failed for '%s' in %s: %s", term, dataset, exc)
            return []
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 4:
            return []
        return payload[3] or []

    def lookup_icd10cm(self, term: str) -> Optional[Dict[str, Optional[str]]]:
        """Return the best ICD-10-CM match for the term.

        Returns dict with keys 'code' and 'display', or None on miss.
        """
        rows = self._search("icd10cm", term, "code", "name")
        if not rows:
            return None
        code, display = rows[0][0], rows[0][1]
        return {"code": code, "display": display}

    def lookup_hcpcs(self, term: str) -> Optional[Dict[str, Optional[str]]]:
        """Return the best HCPCS Level II match for the term.

        Returns dict with keys 'code' and 'display', or None on miss.
        """
        rows = self._search("hcpcs", term, "code", "short_desc")
        if not rows:
            return None
        code, display = rows[0][0], rows[0][1]
        return {"code": code, "display": display}
