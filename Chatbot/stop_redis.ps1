# PowerShell script to stop Redis Docker container

Write-Host "Stopping Redis server..." -ForegroundColor Yellow

docker stop redis-medai

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Redis stopped" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to stop Redis (container may not exist)" -ForegroundColor Red
}

