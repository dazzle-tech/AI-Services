# Script to restart the medication validation service
Write-Host "Restarting Medication Test Orders Validation Service..." -ForegroundColor Cyan
Write-Host ("=" * 60)

# Stop existing service
Write-Host "`n[1/3] Stopping existing service..." -ForegroundColor Yellow
$port = netstat -ano | findstr :8000
if ($port) {
    $pid = ($port -split '\s+')[-1]
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $pid -Force
        Write-Host "   Stopped process (PID: $pid)" -ForegroundColor Green
        Start-Sleep -Seconds 2
    }
} else {
    Write-Host "   No existing service found" -ForegroundColor Gray
}

# Wait a moment
Write-Host "`n[2/3] Waiting for port to be released..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

# Start new service
Write-Host "`n[3/3] Starting service..." -ForegroundColor Yellow
Write-Host "   Service will run on: http://localhost:8000" -ForegroundColor Cyan
Write-Host "   Press Ctrl+C to stop the service`n" -ForegroundColor Gray

# Change to the service directory
Set-Location $PSScriptRoot

# Start the service
python main.py

