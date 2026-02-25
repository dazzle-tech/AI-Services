# VM Deployment Requirements - Windows

This document outlines the recommended VM specifications needed to deploy all AI services on a Windows virtual machine.

## Services Overview

### 1. Chatbot Service (4 Microservices)
- **Orchestrator**: Port 8000
- **SQL Generator**: Port 8001
- **Validator**: Port 8002
- **Formatter**: Port 8003

### 2. AI Auto-Population Service
- **Port**: 8006

### 3. Recommendations Service
- **Port**: 8004

### 4. Summarization Service
- **Port**: 8007

### 5. Medication Test Orders Validation
- **Port**: 8005

### 6. Medical Guideline Validation
- **Port**: 8008

### 7. Discharge Report Generator
- **Port**: 8009

### 8. Quality Discharge Report
- **Port**: 8010

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
| Chatbot Orchestrator | 8000 | Main entry point |
| Chatbot SQL Generator | 8001 | Internal service |
| Chatbot Validator | 8002 | Internal service |
| Chatbot Formatter | 8003 | Internal service |
| Recommendations | 8004 | Standalone service |
| Medication Validation | 8005 | Standalone service |
| AI Auto-Population | 8006 | Standalone service |
| Summarization | 8007 | Standalone service |
| Medical Guideline Validation | 8008 | Standalone service |
| Discharge Report Generator | 8009 | Standalone service |
| Quality Discharge Report | 8010 | Standalone service |
| Redis | 6379 | Infrastructure |
| PostgreSQL | 5432 | Infrastructure (optional) |
| HTTP/HTTPS | 80, 443 | Reverse proxy (if used) |

## Windows Firewall Configuration

### PowerShell Commands
```powershell
# Allow HTTP
New-NetFirewallRule -DisplayName "HTTP" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow

# Allow HTTPS
New-NetFirewallRule -DisplayName "HTTPS" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow

# Allow service ports
New-NetFirewallRule -DisplayName "AI Services" -Direction Inbound -LocalPort 8000-8010 -Protocol TCP -Action Allow

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
