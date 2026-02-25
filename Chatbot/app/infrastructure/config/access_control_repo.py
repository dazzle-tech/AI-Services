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
        data = self.load()
        user = data.get(user_id)
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
        return data.get(user_id)


# Global instance
_access_control_repo = AccessControlRepository()


def load_access_control() -> Dict[str, Any]:
    """Legacy function for backward compatibility."""
    return _access_control_repo.load()


def get_role_for_user(user_id: str) -> Optional[str]:
    """Legacy function for backward compatibility."""
    return _access_control_repo.get_user_role(user_id)



