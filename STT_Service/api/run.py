"""Convenience launcher — equivalent to `python -m app.main`."""
from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8013"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
