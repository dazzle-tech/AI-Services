# Start ICU Summarizer Server
Write-Host "Starting ICU Summarizer API Server..." -ForegroundColor Cyan
Write-Host ""

# Start server using main.py (same as ai-auto-population)
Write-Host "Server will be available at: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "API Documentation: http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

python main.py
