"""Simple script to run the server from project root."""

import uvicorn
from src.main import app

if __name__ == "__main__":
    print("Starting Discharge QA Service...")
    print("Server will be available at: http://localhost:8000")
    print("API docs at: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)

