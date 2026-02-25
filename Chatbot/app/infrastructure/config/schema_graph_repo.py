"""Schema graph configuration repository."""
import json
import os
import logging
import sqlite3
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class SchemaGraphRepository:
    """Repository for loading and managing schema graph configuration."""
    
    def __init__(self, schema_graph_path: Optional[str] = None, db_path: Optional[str] = None):
        self.schema_graph_path = schema_graph_path or settings.schema_graph_path
        self.db_path = db_path or settings.hospital_db_path
    
    def extract_from_db(self, db_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Build a schema graph from SQLite database.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            Schema graph dictionary with tables, columns, and foreign keys
        """
        db_path = db_path or self.db_path
        graph: Dict[str, Dict[str, Any]] = {}
        
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            
            # Get all tables
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [r[0] for r in cur.fetchall()]
            
            for t in tables:
                # Get columns
                cur.execute(f"PRAGMA table_info({t});")
                cols = [r[1] for r in cur.fetchall()]
                
                # Get foreign keys
                cur.execute(f"PRAGMA foreign_key_list({t});")
                fks = [{"from": r[3], "to_table": r[2], "to_col": r[4]} for r in cur.fetchall()]
                
                graph[t] = {"columns": cols, "foreign_keys": fks}
            
            conn.close()
            logger.info(f"✅ Extracted schema graph with {len(graph)} tables.")
        except Exception as e:
            logger.warning(f"⚠️ Failed to extract schema graph: {e}")
        
        return graph
    
    def load_or_create(self) -> Dict[str, Dict[str, Any]]:
        """
        Load schema graph from cache or extract from database.
        
        Returns:
            Schema graph dictionary
        """
        if os.path.exists(self.schema_graph_path):
            try:
                with open(self.schema_graph_path, "r", encoding="utf-8") as f:
                    graph = json.load(f)
                    if isinstance(graph, dict) and graph:
                        logger.info(f"🧠 Loaded cached schema graph from {self.schema_graph_path}")
                        return graph
            except Exception as e:
                logger.warning(f"⚠️ Failed to load cached schema graph: {e}")
        
        logger.info("🛠️ Building new schema graph...")
        graph = self.extract_from_db()
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.schema_graph_path) or ".", exist_ok=True)
            with open(self.schema_graph_path, "w", encoding="utf-8") as f:
                json.dump(graph, f, indent=2)
            logger.info(f"💾 Saved schema graph to {self.schema_graph_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not save schema graph: {e}")
        
        return graph


# Global instance
_schema_graph_repo = SchemaGraphRepository()


def load_or_create_schema_graph() -> Dict[str, Dict[str, Any]]:
    """Legacy function for backward compatibility."""
    return _schema_graph_repo.load_or_create()



