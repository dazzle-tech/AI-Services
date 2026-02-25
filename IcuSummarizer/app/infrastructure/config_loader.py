"""Configuration loader for mappings and settings"""
from pathlib import Path
from typing import Dict, Any
import yaml
from app.utils.errors import ConfigurationError


def load_yaml_config(config_path: Path) -> Dict[str, Any]:
    """Load YAML configuration file"""
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {config_path}: {str(e)}")
    except Exception as e:
        raise ConfigurationError(f"Error loading {config_path}: {str(e)}")
