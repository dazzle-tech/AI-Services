"""Access control configuration repository."""
import json
import os
import logging
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class AccessControlRepository:
    """Repository for loading and accessing access control configuration."""
    
    def __init__(self, path: Optional[str] = None):
        self.path = path or settings.access_control_path
        self._legacy_format_warned = False
    
    def load(self) -> Dict[str, Any]:
        """
        Load access control configuration from JSON file.
        
        Returns:
            Access control dictionary
            
        Raises:
            FileNotFoundError: If access_control.json doesn't exist
            json.JSONDecodeError: If file is invalid JSON
        """
        if not os.path.exists(self.path):
            logger.warning(f"⚠️ access_control.json not found at {self.path}")
            return {}
        
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"✅ Loaded access control from {self.path}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse access_control.json: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to read access_control.json: {e}")
            raise
    
    def get_user_role(self, user_id: str) -> Optional[str]:
        """
        Get role for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Role string or None if user not found
        """
        user = self.get_user_access(user_id)
        if not user:
            return None
        return user.get("role")
    
    def get_user_access(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full access configuration for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            User access configuration or None if user not found
        """
        data = self.load()
        if not data:
            return None

        direct_user = data.get(user_id)
        if isinstance(direct_user, dict):
            cfg = dict(direct_user)
            cfg.setdefault("role", self._default_role_for_user(user_id))
            return self._apply_schema_deprecations(cfg)

        nested_users = data.get("users")
        if isinstance(nested_users, dict):
            nested_user = nested_users.get(user_id)
            if isinstance(nested_user, dict):
                cfg = dict(nested_user)
                cfg.setdefault("role", self._default_role_for_user(user_id))
                return self._apply_schema_deprecations(cfg)

        # Backward-compatible format: single shared policy object without per-user keys.
        if self._looks_like_shared_policy(data):
            if not self._legacy_format_warned:
                logger.warning(
                    "access_control.json has shared-policy format; applying policy to all users."
                )
                self._legacy_format_warned = True
            cfg = dict(data)
            cfg.setdefault("role", self._default_role_for_user(user_id))
            return self._apply_schema_deprecations(cfg)

        return None

    def _apply_schema_deprecations(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply compatibility/deprecation rules to the allowed schema.

        Some deployments have migrated to `patient_encounters`/`patients` while older prompts and
        generators may still try to use `ap_patient`. When the modern encounter table exists,
        treat `ap_patient` as deprecated to prevent accidental use and execution-time failures.

        However, `ap_patient` can contain legacy demographic attributes (e.g. `blood_group_lkey`)
        that are not always present in modern `patients`. Only deprecate it when `patients`
        appears to cover the relevant fields.
        """
        allowed_schema = cfg.get("allowed_schema")
        if not isinstance(allowed_schema, dict):
            return cfg

        if "patient_encounters" in allowed_schema and "ap_patient" in allowed_schema:
            patients_cols = {
                str(c).lower()
                for c in (allowed_schema.get("patients", {}) or {}).get("columns", [])
            }
            ap_cols = {
                str(c).lower()
                for c in (allowed_schema.get("ap_patient", {}) or {}).get("columns", [])
            }

            legacy_only_cols = {
                # Commonly-requested attributes that frequently live only in ap_* schemas
                "blood_group_lkey",
                "gender_lkey",
            }
            needs_ap_patient = any((c in ap_cols) and (c not in patients_cols) for c in legacy_only_cols)

            if not needs_ap_patient:
                allowed_schema = dict(allowed_schema)
                allowed_schema.pop("ap_patient", None)
                cfg = dict(cfg)
                cfg["allowed_schema"] = allowed_schema
        return cfg

    def _looks_like_shared_policy(self, data: Dict[str, Any]) -> bool:
        """Detect legacy/shared policy format."""
        return (
            isinstance(data, dict)
            and isinstance(data.get("allowed_schema"), dict)
            and isinstance(data.get("allowed_operations"), list)
        )

    def _default_role_for_user(self, user_id: str) -> str:
        """Resolve role for users when config has no explicit per-user role."""
        raw_map = os.environ.get("ACCESS_CONTROL_ROLE_MAP", "").strip()
        if raw_map:
            for item in raw_map.split(","):
                pair = item.strip()
                if not pair or ":" not in pair:
                    continue
                uid, role = pair.split(":", 1)
                if uid.strip() == user_id and role.strip():
                    return role.strip()

        admin_users = {
            u.strip()
            for u in os.environ.get("ACCESS_CONTROL_ADMIN_USERS", "admin").split(",")
            if u.strip()
        }
        if user_id in admin_users:
            return "admin"

        return os.environ.get("ACCESS_CONTROL_DEFAULT_ROLE", "doctor").strip() or "doctor"


# Global instance
_access_control_repo = AccessControlRepository()


def load_access_control() -> Dict[str, Any]:
    """Legacy function for backward compatibility."""
    return _access_control_repo.load()


def get_role_for_user(user_id: str) -> Optional[str]:
    """Legacy function for backward compatibility."""
    return _access_control_repo.get_user_role(user_id)



