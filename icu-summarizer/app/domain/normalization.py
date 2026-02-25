"""Normalization - Map item names/codes to canonical clinical concepts"""
from typing import Dict, Optional, List
import yaml
from pathlib import Path


class ConceptNormalizer:
    """Maps flowsheet item names/codes to canonical clinical concepts"""
    
    def __init__(self, mappings: Dict[str, Dict[str, str]]):
        """
        Initialize with mappings dictionary.
        
        Expected structure:
        {
            "concept_name": {
                "item_names": ["name1", "name2"],
                "item_codes": ["code1", "code2"]
            }
        }
        """
        self.mappings = mappings
        self._build_lookup()
    
    def _build_lookup(self):
        """Build reverse lookup maps for fast matching"""
        self._name_to_concept: Dict[str, str] = {}
        self._code_to_concept: Dict[str, str] = {}
        
        for concept, mapping in self.mappings.items():
            # Map item names
            for name in mapping.get("item_names", []):
                normalized_name = name.lower().strip()
                self._name_to_concept[normalized_name] = concept
            
            # Map item codes
            for code in mapping.get("item_codes", []):
                normalized_code = code.lower().strip()
                self._code_to_concept[normalized_code] = concept
    
    def normalize(self, item_name: str, item_code: Optional[str] = None) -> Optional[str]:
        """
        Normalize an item to a canonical concept.
        
        Args:
            item_name: The item name from flowsheet
            item_code: Optional item code
            
        Returns:
            Canonical concept name or None if no mapping found
        """
        # Try code first (more specific)
        if item_code:
            normalized_code = item_code.lower().strip()
            if normalized_code in self._code_to_concept:
                return self._code_to_concept[normalized_code]
        
        # Try name
        normalized_name = item_name.lower().strip()
        if normalized_name in self._name_to_concept:
            return self._name_to_concept[normalized_name]
        
        # Try partial matches (contains)
        for name_key, concept in self._name_to_concept.items():
            if name_key in normalized_name or normalized_name in name_key:
                return concept
        
        return None
    
    def get_all_concepts(self) -> List[str]:
        """Get list of all canonical concepts"""
        return list(self.mappings.keys())


def load_mappings_from_yaml(yaml_path: Path) -> Dict[str, Dict[str, str]]:
    """
    Load mappings from YAML file.
    
    Expected YAML structure:
    concept_name:
      item_names:
        - "name1"
        - "name2"
      item_codes:
        - "code1"
        - "code2"
    """
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data or {}
