# PowerShell script to start Redis using Docker
# Make sure Docker Desktop is running first!

Write-Host "Starting Redis server using Docker..." -ForegroundColor Green

# Check if Redis container already exists
$existing = docker ps -a --filter "name=redis-medai" --format "{{.Names}}"
if ($existing -eq "redis-medai") {
    Write-Host "Redis container already exists. Starting it..." -ForegroundColor Yellow
    docker start redis-medai
} else {
    Write-Host "Creating new Redis container..." -ForegroundColor Yellow
    docker run -d --name redis-medai -p 6379:6379 redis:7-alpine
}

# Wait a moment for Redis to start
Start-Sleep -Seconds 2

# Test connection
Write-Host "`nTesting Redis connection..." -ForegroundColor Cyan
docker exec redis-medai redis-cli ping

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Redis is running on localhost:6379" -ForegroundColor Green
    Write-Host "To stop Redis: docker stop redis-medai" -ForegroundColor Gray
    Write-Host "To remove Redis: docker rm redis-medai" -ForegroundColor Gray
} else {
    Write-Host "`n❌ Failed to connect to Redis. Check Docker Desktop is running." -ForegroundColor Red
}

