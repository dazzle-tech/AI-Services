"""Quality rule loaders."""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from .entities import QualityRules


def load_quality_rules(rules_dir: Optional[Path] = None) -> QualityRules:
    """Load quality rules from JSON files."""
    if rules_dir is None:
        rules_dir = Path(__file__).parent.parent.parent / "docs" / "quality_rules"
    
    rules = QualityRules()
    
    for rule_type in ["completeness", "consistency", "safety", "structure"]:
        rule_file = rules_dir / f"{rule_type}.json"
        if rule_file.exists():
            with open(rule_file, "r") as f:
                setattr(rules, rule_type, json.load(f))
    
    return rules


def load_rules_from_dict(rules_dict: Dict[str, Any]) -> QualityRules:
    """Load quality rules from a dictionary."""
    return QualityRules(**rules_dict)

