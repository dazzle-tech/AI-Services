# Redis Setup Guide for MedAI Assistant

This guide explains how to set up and run Redis for session memory storage.

## Quick Start (Docker - Recommended)

### Prerequisites
- Docker Desktop installed and running

### Steps

1. **Start Docker Desktop** (if not already running)

2. **Start Redis** using the provided script:
   ```powershell
   .\start_redis.ps1
   ```

   Or manually:
   ```powershell
   docker run -d --name redis-medai -p 6379:6379 redis:7-alpine
   ```

3. **Verify Redis is running**:
   ```powershell
   docker exec redis-medai redis-cli ping
   ```
   Should return: `PONG`

4. **Stop Redis** (when done):
   ```powershell
   .\stop_redis.ps1
   ```
   Or: `docker stop redis-medai`

## Alternative Methods

### Option 2: WSL (Windows Subsystem for Linux)

If you have WSL installed:

```bash
# In WSL terminal
sudo apt-get update
sudo apt-get install redis-server
redis-server
```

### Option 3: Memurai (Windows Native Redis)

1. Download Memurai from: https://www.memurai.com/
2. Install and start the service
3. It runs on `localhost:6379` by default

### Option 4: Cloud Redis (Production)

For production, consider:
- **Redis Cloud**: https://redis.com/cloud/
- **Azure Cache for Redis**: https://azure.microsoft.com/en-us/services/cache/
- **AWS ElastiCache**: https://aws.amazon.com/elasticache/

## Configuration

Redis connection is configured via environment variables (defaults shown):

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
SESSION_TTL_SECONDS=86400  # 24 hours
```

Create a `.env` file in the `chatbot` directory to override defaults:

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
SESSION_TTL_SECONDS=86400
```

## Testing Redis Connection

Test from Python:

```python
import redis
r = redis.Redis(host='localhost', port=6379, db=0)
r.ping()  # Should return True
```

Or use the Redis CLI (if installed):

```powershell
docker exec -it redis-medai redis-cli
> ping
PONG
> keys medai:session:*
(empty list or set)
```

## Troubleshooting

### Docker Desktop Not Running
- Start Docker Desktop from the Start menu
- Wait for it to fully start (whale icon in system tray)

### Port 6379 Already in Use
- Check if Redis is already running: `docker ps`
- Use a different port: `docker run -d --name redis-medai -p 6380:6379 redis:7-alpine`
- Update `REDIS_PORT=6380` in your `.env` file

### Connection Refused
- Verify Redis is running: `docker ps`
- Check Redis logs: `docker logs redis-medai`
- Verify port mapping: `docker port redis-medai`

### App Works Without Redis
- The app has fallback mode - it will work but sessions won't persist
- Check logs for Redis connection warnings
- Install Redis Python client: `pip install redis`

## Redis Commands (Useful for Debugging)

```powershell
# View all session keys
docker exec redis-medai redis-cli KEYS "medai:session:*"

# View a specific session
docker exec redis-medai redis-cli GET "medai:session:session_123"

# Check TTL of a session
docker exec redis-medai redis-cli TTL "medai:session:session_123"

# Clear all sessions (same as /reset_sessions endpoint)
docker exec redis-medai redis-cli --eval "return redis.call('del', unpack(redis.call('keys', 'medai:session:*')))" 0

# Monitor Redis commands in real-time
docker exec redis-medai redis-cli MONITOR
```

## Production Considerations

1. **Persistence**: Docker Redis runs in-memory by default. For production:
   ```powershell
   docker run -d --name redis-medai -p 6379:6379 -v redis-data:/data redis:7-alpine redis-server --appendonly yes
   ```

2. **Password Protection**: Add authentication:
   ```powershell
   docker run -d --name redis-medai -p 6379:6379 redis:7-alpine redis-server --requirepass yourpassword
   ```
   Then set `REDIS_PASSWORD=yourpassword` in your `.env` (requires updating `session_store.py`)

3. **Memory Limits**: Set max memory:
   ```powershell
   docker run -d --name redis-medai -p 6379:6379 redis:7-alpine redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
   ```

