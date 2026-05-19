# MedAI Assistant - Refactored Structure

This document describes the refactored layered architecture of the MedAI Assistant chatbot project, following the structure pattern of `summarization_service`.

## Project Structure

```
chatbot/
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── chat.py              # Chat endpoints
│   │       ├── admin.py              # Admin audit endpoints
│   │       ├── patient_details.py    # Patient details endpoint
│   │       ├── sql_generator.py      # SQL generator endpoint
│   │       ├── validator.py          # Validator endpoint
│   │       └── formatter.py         # Formatter endpoint
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py                # Configuration management
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py                # Pydantic request/response models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat_orchestrator.py     # Main chat orchestration logic
│   │   ├── session_memory.py        # Session memory management
│   │   ├── intent.py                 # Intent detection
│   │   ├── correction.py              # Spelling correction
│   │   ├── scope.py                  # Query scope detection
│   │   ├── entities.py               # Entity extraction
│   │   ├── patient_details.py        # Patient details SQL builder
│   │   ├── sql_generation.py         # SQL generation logic
│   │   ├── validation.py             # SQL validation logic
│   │   └── formatting.py             # Result formatting logic
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   └── ollama_client.py      # Ollama LLM client wrapper
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── hospital_repo.py      # Hospital DB repository
│   │   │   └── audit_repo.py         # Audit DB repository
│   │   ├── http/
│   │   │   ├── __init__.py
│   │   │   └── clients.py            # HTTP client utilities
│   │   └── config/
│   │       ├── __init__.py
│   │       ├── access_control_repo.py # Access control config repo
│   │       └── schema_graph_repo.py  # Schema graph config repo
│   └── crewai/
│       ├── __init__.py
│       ├── crew.py                   # CrewAI crew definition
│       └── tools.py                  # CrewAI tools
├── data/                             # Data files (dev/testing)
│   ├── hospital.db                   # Mock clinical database
│   ├── medai_audit.db                # Audit/history database
│   ├── access_control.json           # Access control configuration
│   ├── schema_graph.json             # Schema graph configuration
│   └── sessions_memory.json          # Session memory (persistent)
├── runners/                          # Service entry points
│   ├── main_orchestrator.py          # Orchestrator service entry point
│   ├── main_sql_generator.py        # SQL generator service entry point
│   ├── main_validator.py            # Validator service entry point
│   └── main_formatter.py            # Formatter service entry point
├── scripts/
│   └── init_mock_db.py               # Initialize mock database
├── web/
│   └── index.html                    # Frontend UI
└── requirements.txt                  # Python dependencies
```

## Architecture Layers

### 1. API Layer (`app/api/routes/`)
- **Purpose**: FastAPI route handlers - thin layer that delegates to services
- **Files**:
  - `chat.py`: Main chat endpoint, CrewAI endpoint, session management
  - `admin.py`: Admin audit endpoints (history, search, events)
  - `patient_details.py`: Patient details endpoint
  - `sql_generator.py`: SQL generation endpoint
  - `validator.py`: SQL validation endpoint
  - `formatter.py`: Result formatting endpoint

### 2. Domain Services Layer (`app/services/`)
- **Purpose**: Business logic and domain services
- **Key Services**:
  - `chat_orchestrator.py`: Main orchestration logic for chat pipeline
  - `session_memory.py`: Session state management
  - `intent.py`: Intent detection (data/social/chat)
  - `correction.py`: Spelling/grammar correction
  - `scope.py`: Query scope detection (specific vs general)
  - `entities.py`: Entity extraction (medical_record_number/MRN, patient_name, etc.)
  - `patient_details.py`: Role-based patient details SQL builder
  - `sql_generation.py`: SQL generation from natural language
  - `validation.py`: SQL validation and execution
  - `formatting.py`: Result formatting and summarization

### 3. Infrastructure Layer (`app/infrastructure/`)
- **Purpose**: External adapters, repositories, and clients
- **Components**:
  - `llm/ollama_client.py`: Ollama LLM client wrapper
  - `db/hospital_repo.py`: Hospital database repository
  - `db/audit_repo.py`: Audit database repository
  - `http/clients.py`: HTTP client utilities for service-to-service calls
  - `config/access_control_repo.py`: Access control configuration loader
  - `config/schema_graph_repo.py`: Schema graph configuration loader

### 4. Models Layer (`app/models/`)
- **Purpose**: Pydantic schemas for request/response validation
- **File**: `schemas.py` - Contains all request/response models

### 5. Core Layer (`app/core/`)
- **Purpose**: Configuration and shared utilities
- **File**: `config.py` - Settings management using Pydantic

### 6. CrewAI Layer (`app/crewai/`)
- **Purpose**: CrewAI integration for advanced routing
- **Files**:
  - `crew.py`: CrewAI crew and agent definitions
  - `tools.py`: CrewAI tools (SQL generator, validator, formatter)

## Service Entry Points

Each service has its own entry point in the `runners/` directory:

1. **Orchestrator** (`runners/main_orchestrator.py`): Port 8000
   - Main chat endpoint
   - Admin audit endpoints
   - Patient details endpoint
   - Session management

2. **SQL Generator** (`runners/main_sql_generator.py`): Port 8001
   - SQL generation from natural language

3. **Validator** (`runners/main_validator.py`): Port 8002
   - SQL validation and execution

4. **Formatter** (`runners/main_formatter.py`): Port 8003
   - Result formatting and summarization

## Running the Services

### Development Mode

**Important:** Run all commands from the `chatbot/` directory.

**Auto-Reload:** By default, all services have auto-reload enabled. When you make code changes, the services will automatically restart. You'll see a message like "Reloading..." in the terminal when changes are detected.

To disable auto-reload (for production), set the environment variable:
```bash
export API_RELOAD=false
# Or on Windows PowerShell:
$env:API_RELOAD="false"
```

```bash
# Navigate to chatbot directory first
cd chatbot

# Terminal 1: Orchestrator
python runners/main_orchestrator.py

# Terminal 2: SQL Generator
python runners/main_sql_generator.py

# Terminal 3: Validator
python runners/main_validator.py

# Terminal 4: Formatter
python runners/main_formatter.py
```

**Note:** Auto-reload watches for changes in Python files. When you save a file, the service will automatically restart within a few seconds.

Alternatively, you can run from the root `AI-Services` directory:

```bash
# Terminal 1: Orchestrator
python chatbot/runners/main_orchestrator.py

# Terminal 2: SQL Generator
python chatbot/runners/main_sql_generator.py

# Terminal 3: Validator
python chatbot/runners/main_validator.py

# Terminal 4: Formatter
python chatbot/runners/main_formatter.py
```

### Using Environment Variables

All services respect environment variables for configuration (see `app/core/config.py`):

- `SQL_GEN_URL`: SQL generator service URL
- `VALIDATOR_URL`: Validator service URL
- `FORMATTER_URL`: Formatter service URL
- `OLLAMA_HOST`: Ollama server host
- `LLM_MODEL`: LLM model name
- `HOSPITAL_SQLITE_PATH`: Path to hospital.db
- `AUDIT_DB_PATH`: Path to medai_audit.db
- `ACCESS_CONTROL_PATH`: Path to access_control.json
- `SCHEMA_GRAPH_PATH`: Path to schema_graph.json
- `SESSIONS_MEMORY_PATH`: Path to sessions_memory.json
- `LOG_LEVEL`: Logging level (INFO, DEBUG, etc.)

## Data Files

All data files are stored in the `data/` directory:

- `hospital.db`: Mock clinical database (SQLite)
- `medai_audit.db`: Audit/history database (SQLite)
- `access_control.json`: User role and permission configuration
- `schema_graph.json`: Database schema graph (auto-generated)
- `sessions_memory.json`: Persistent session memory

## Migration from Old Structure

The old flat structure has been refactored as follows:

- `chat_orchestrator_service.py` → `app/api/routes/chat.py` + `app/services/chat_orchestrator.py`
- `sql_generator_service.py` → `app/api/routes/sql_generator.py` + `app/services/sql_generation.py`
- `validator_service.py` → `app/api/routes/validator.py` + `app/services/validation.py`
- `result_formating.py` → `app/api/routes/formatter.py` + `app/services/formatting.py`
- `medai_crewai_crew.py` → `app/crewai/crew.py`
- `medai_crewai_tools.py` → `app/crewai/tools.py`

## Benefits of New Structure

1. **Separation of Concerns**: API routes are thin, business logic is in services
2. **Testability**: Services can be tested independently
3. **Maintainability**: Clear organization makes it easier to find and modify code
4. **Reusability**: Infrastructure components can be reused across services
5. **Scalability**: Easy to add new services or extend existing ones
6. **Consistency**: Follows the same pattern as `summarization_service`

## Next Steps

1. Complete SQL generation service implementation (derived fields, auto-qualification, etc.)
2. Add comprehensive unit tests for each service
3. Add integration tests for the full pipeline
4. Consider adding dependency injection container
5. Add API documentation with OpenAPI/Swagger

