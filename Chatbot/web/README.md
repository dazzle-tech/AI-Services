# MedAI Assistant Frontend

## Quick Start

### Option 1: Open Directly in Browser (Simplest)

1. Make sure the orchestrator service is running:
   ```bash
   cd chatbot
   python runners/main_orchestrator.py
   ```

2. Open `index.html` in your browser:
   - Double-click `index.html` in your file explorer, OR
   - Right-click → Open with → Your browser (Chrome, Firefox, Edge, etc.)

The frontend will connect to `http://127.0.0.1:8000` (the orchestrator service).

### Option 2: Serve with Python HTTP Server (Recommended for Development)

1. Navigate to the `web` directory:
   ```bash
   cd chatbot/web
   ```

2. Start a simple HTTP server:
   ```bash
   # Python 3
   python -m http.server 8080
   
   # Or if you have Python 2
   python -m SimpleHTTPServer 8080
   ```

3. Open your browser and go to:
   ```
   http://localhost:8080
   ```

### Option 3: Serve with Node.js (if you have Node installed)

1. Install a simple HTTP server globally:
   ```bash
   npm install -g http-server
   ```

2. Navigate to the `web` directory:
   ```bash
   cd chatbot/web
   ```

3. Start the server:
   ```bash
   http-server -p 8080
   ```

4. Open your browser and go to:
   ```
   http://localhost:8080
   ```

## Prerequisites

Before running the frontend, make sure all backend services are running:

1. **Orchestrator** (port 8000) - Required
   ```bash
   python runners/main_orchestrator.py
   ```

2. **SQL Generator** (port 8001) - Required for data queries
   ```bash
   python runners/main_sql_generator.py
   ```

3. **Validator** (port 8002) - Required for data queries
   ```bash
   python runners/main_validator.py
   ```

4. **Formatter** (port 8003) - Required for data queries
   ```bash
   python runners/main_formatter.py
   ```

## Configuration

The frontend is configured to connect to:
- Orchestrator API: `http://127.0.0.1:8000/chat`
- Patient Details API: `http://127.0.0.1:8000/patient_details`
- Reset Sessions API: `http://127.0.0.1:8000/reset_sessions`

If you need to change these URLs, edit the constants in `index.html`:
```javascript
const API_URL = "http://127.0.0.1:8000/chat";
const PATIENT_DETAILS_URL = "http://127.0.0.1:8000/patient_details";
const RESET_URL = "http://127.0.0.1:8000/reset_sessions";
```

## Troubleshooting

- **Connection refused**: Verify the orchestrator service is running on port 8000
- **404 errors**: Check that all backend services are running on their respective ports



