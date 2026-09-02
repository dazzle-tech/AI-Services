# VM Deployment Requirements - Windows

This document outlines the recommended VM specifications needed to deploy all AI services on a Windows virtual machine.

## Services Overview

### Service Ports (Docker Compose / local HTTP)
- **Patient Timeline**: 8001
- **Nurse Task Prioritization**: 8002
- **Lab Result Interpreter**: 8003
- **Smart Discharge Planner**: 8004
- **Discharge Report Generator**: 8005
- **Medication Test Orders Validation**: 8006
- **Recommendations**: 8007
- **Medical Guideline Validation**: 8008
- **Summarization**: 8009
- **AI Auto-Population**: 8010
- **Quality Discharge Report**: 8011
- **OCR Parsing**: 8012
- **ICU Summarizer**: 8013
- **Specialist Alert**: 8014
- **Medical Image Interpretation Assist**: 8015
- **Radiology Image QA AI**: 8016
- **Chatbot Orchestrator API**: 8017
- **Chatbot SQL Generator**: 8018
- **Chatbot Validator**: 8019
- **Chatbot Formatter**: 8020
- **Chatbot WhatsApp Adapter**: 8021
- **Medical Image Template Autofill**: 8022
- **Sepsis Early Detection**: 8023
- **Radiology Report Filling**: 8024
- **Billing Coder**: 8025
- **ConvoScribe**: 8026
- **STT Service (Radiology)**: 8027
- **NurseHandOver**: 8028
- **ORScribe**: 8030
- **System Display Plugin**: 8031
- **Radiology Workflow**: 8090
- **Chatbot UI/Web (if enabled)**: 8080

## Infrastructure Requirements

### Redis
- **Port**: 6379
- **Purpose**: Session management for chatbot service
- **Memory**: ~100-200 MB

### PostgreSQL (Optional)
- **Port**: 5432
- **Purpose**: Hospital database for chatbot (can use SQLite for development)
- **Storage**: Varies based on data size

## Recommended VM Specifications (Windows)

### CPU: 8 cores
- Better concurrent request handling
- Allows for multiple requests per service simultaneously
- Better performance for AI/LLM processing
- Each service runs as a separate Python process (8 services + Redis = 9 processes minimum)

### RAM: 16 GB
- Comfortable headroom for all services
- Base Windows OS: ~2-3 GB
- Python runtime per service: ~200-300 MB each (8 services = ~2-2.5 GB)
- Redis: ~200 MB
- PostgreSQL (if used): ~500 MB
- System overhead: ~2 GB
- **Total**: ~7-8 GB used, 16 GB provides comfortable buffer
- Better caching and performance
- Handles traffic spikes better
- Allows for future scaling

### Storage: 100 GB SSD
- Operating system (Windows): ~20-30 GB
- Python and dependencies: ~2-3 GB
- Application code: ~500 MB
- Logs and data: ~10-20 GB
- **Buffer**: ~50 GB for growth
- Faster I/O for database operations
- Better performance for Redis
- More space for logs, data, and backups
- SSD recommended for better performance

### Network
- **1 Gbps recommended**
- Low latency connection to OpenAI API
- Sufficient bandwidth for concurrent API calls
- All services need internet access for OpenAI API calls

## Operating System

### Recommended
- **Windows Server 2022** or **Windows Server 2019**
  - Long-term support
  - Better for production environments
  - Enterprise features available

### Alternative
- **Windows 11 Pro** (for development/testing)
- **Windows 10 Pro** (for development/testing)

## Software Dependencies

### Python
- **Python 3.10+** (required for all services)
- Download from [python.org](https://www.python.org/downloads/)
- Ensure "Add Python to PATH" is checked during installation
- All services use FastAPI which requires Python 3.8+

### Redis for Windows
- **Option 1**: Use WSL2 (Windows Subsystem for Linux) and install Redis in Linux
- **Option 2**: Use Memurai (Redis-compatible for Windows) - [memurai.com](https://www.memurai.com/)
- **Option 3**: Use Docker Desktop for Windows and run Redis container

### PostgreSQL (Optional)
- Download from [postgresql.org](https://www.postgresql.org/download/windows/)
- Or use Docker Desktop for Windows

### Process Management
- **Windows Service** (using NSSM - Non-Sucking Service Manager)
- **Task Scheduler** (for scheduled tasks)
- **IIS** (Internet Information Services) - optional for reverse proxy

### Reverse Proxy (Optional)
- **IIS** with URL Rewrite module
- **Nginx for Windows** - [nginx.org](https://nginx.org/en/download.html)
- **Caddy** - [caddyserver.com](https://caddyserver.com/)

### Additional Tools
- **Git for Windows** - [git-scm.com](https://git-scm.com/download/win)
- **Docker Desktop for Windows** (optional but recommended)
- **PowerShell 7+** (for scripting and automation)

## Port Allocation Summary

| Service | Port | Notes |
|---------|------|-------|
| Patient Timeline | 8001 | Standalone service |
| Nurse Task Prioritization | 8002 | Standalone service |
| Lab Result Interpreter | 8003 | Standalone service |
| Smart Discharge Planner | 8004 | Standalone service |
| Discharge Report Generator | 8005 | Standalone service |
| Medication Test Orders Validation | 8006 | Standalone service |
| Recommendations | 8007 | Standalone service |
| Medical Guideline Validation | 8008 | Standalone service |
| Summarization | 8009 | Standalone service |
| AI Auto-Population | 8010 | Standalone service |
| Quality Discharge Report | 8011 | Standalone service |
| OCR Parsing | 8012 | Standalone service |
| ICU Summarizer | 8013 | Standalone service |
| Specialist Alert | 8014 | Standalone service |
| Medical Image Interpretation Assist | 8015 | Standalone service |
| Radiology Image QA AI | 8016 | Standalone service |
| Chatbot Orchestrator API | 8017 | Standalone service |
| Chatbot SQL Generator | 8018 | Chatbot subprocess |
| Chatbot Validator | 8019 | Chatbot subprocess |
| Chatbot Formatter | 8020 | Chatbot subprocess |
| Chatbot WhatsApp Adapter | 8021 | Chatbot subprocess |
| Medical Image Template Autofill | 8022 | Standalone service |
| Sepsis Early Detection | 8023 | Standalone service |
| Radiology Report Filling | 8024 | Standalone service |
| Billing Coder | 8025 | Standalone service |
| ConvoScribe | 8026 | Standalone service |
| STT Service (Radiology) | 8027 | Standalone service |
| NurseHandOver | 8028 | Standalone service |
| ORScribe | 8030 | Standalone service |
| System Display Plugin | 8031 | Standalone service |
| Radiology Workflow | 8090 | Standalone service |
| Chatbot UI/Web | 8080 | Optional |
| Redis | 6379 | Infrastructure (host mapping differs per compose) |
| PostgreSQL | 5432 | Infrastructure (host mapping differs per compose) |
| HTTP/HTTPS | 80, 443 | Reverse proxy (if used) |

## Windows Firewall Configuration

### PowerShell Commands
```powershell
# Allow HTTP
New-NetFirewallRule -DisplayName "HTTP" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow

# Allow HTTPS
New-NetFirewallRule -DisplayName "HTTPS" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow

# Allow service ports
New-NetFirewallRule -DisplayName "AI Services" -Direction Inbound -LocalPort 8001-8031,8080,8090 -Protocol TCP -Action Allow

# Allow Redis (internal only - restrict to localhost)
New-NetFirewallRule -DisplayName "Redis" -Direction Inbound -LocalPort 6379 -Protocol TCP -Action Allow -RemoteAddress 127.0.0.1
```

### Recommended Architecture
- **IIS or Nginx** as reverse proxy on ports 80/443
- All services accessible through reverse proxy with different paths
- Services only accessible from localhost (127.0.0.1)
- SSL/TLS termination at reverse proxy

## Resource Usage Estimates

### Per Service (Average)
- **CPU**: 5-15% per core (idle: ~1-2%, active: 10-20%)
- **RAM**: 200-400 MB per service
- **Network**: Varies based on OpenAI API calls (can be 1-10 MB per request)

### Total System Load (All Services Running)
- **Idle**: 
  - CPU: 10-20%
  - RAM: ~4-5 GB
  - Network: Minimal
  
- **Moderate Load** (10-20 concurrent requests):
  - CPU: 40-60%
  - RAM: ~6-8 GB
  - Network: 10-50 Mbps
  
- **High Load** (50+ concurrent requests):
  - CPU: 80-100%
  - RAM: ~10-12 GB
  - Network: 50-200 Mbps

## Quick Reference

**Recommended VM**: 8 CPU, 16 GB RAM, 100 GB SSD

**Total Services**: 11 (8 application services + Redis + PostgreSQL + Reverse Proxy)
**Total Ports Used**: 13 (11 service ports + 2 infrastructure ports)

**Operating System**: Windows Server 2022 or Windows 11/10 Pro
**Python Version**: 3.10+
**Network**: 1 Gbps recommended
