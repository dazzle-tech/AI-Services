"""Main entry point for the ICU Summarizer Service."""
import logging
from pathlib import Path
import os
import sys

# Set Python path before importing app
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
os.environ["PYTHONPATH"] = str(project_root)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Import app after setting PYTHONPATH
from app.main import app

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting ICU Summarizer API Server...")
    logger.info("Server will be available at: http://127.0.0.1:8000")
    logger.info("API Documentation: http://127.0.0.1:8000/docs")
    
    # Use import string for reload to work properly
    # Try port 8000, fallback to 8001 if busy
    import socket
    
    def is_port_available(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return True
            except OSError:
                return False
    
    port = 8000
    if not is_port_available(port):
        logger.warning(f"Port {port} is in use, trying port 8001...")
        port = 8001
        if not is_port_available(port):
            logger.error("Both ports 8000 and 8001 are in use. Please free a port.")
            sys.exit(1)
    
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=True,
        log_level="info"
    )
