# Script to stop the medication validation service
Write-Host "Checking for service on port 8000..." -ForegroundColor Yellow

$port = netstat -ano | findstr :8000
if ($port) {
    $pid = ($port -split '\s+')[-1]
    Write-Host "Found process on port 8000 (PID: $pid)" -ForegroundColor Yellow
    
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "Stopping process: $($process.ProcessName) (PID: $pid)..." -ForegroundColor Yellow
        Stop-Process -Id $pid -Force
        Write-Host "Service stopped successfully!" -ForegroundColor Green
    } else {
        Write-Host "Process not found (may have already stopped)" -ForegroundColor Yellow
    }
} else {
    Write-Host "No process found on port 8000" -ForegroundColor Green
}

Write-Host "`nYou can now start the service with: python main.py" -ForegroundColor Cyan

