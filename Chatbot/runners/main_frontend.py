"""Main entry point for static frontend service."""
import logging
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


chatbot_dir = Path(__file__).parent.parent
web_dir = chatbot_dir / "web"

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | frontend | %(message)s",
)
logger = logging.getLogger(__name__)


class FrontendHandler(SimpleHTTPRequestHandler):
    """Serve files from the web directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(web_dir), **kwargs)

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)


def main() -> int:
    if not web_dir.exists():
        logger.error("Frontend directory not found: %s", web_dir)
        return 1

    host = os.getenv("FRONTEND_HOST", os.getenv("API_HOST", "0.0.0.0"))
    port = int(os.getenv("FRONTEND_PORT", "8080"))

    logger.info("Starting frontend on http://%s:%s", host, port)
    logger.info("Serving static files from %s", web_dir)

    server = ThreadingHTTPServer((host, port), FrontendHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down frontend server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
