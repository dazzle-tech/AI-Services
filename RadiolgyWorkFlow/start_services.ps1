param(
  [switch]$Visible
)

$services = @(
  @{ Name = 'RadiologyImageQaAI';     Wd = 'C:\Users\User\Desktop\AI-Services\RadiologyImageQaAI'; Port = 8016; Health = 'http://127.0.0.1:8016/health' },
  @{ Name = 'InterpretationAssist';   Wd = 'C:\Users\User\Desktop\AI-Services\MedicalImageInterpretationAssistService'; Port = 8015; Health = 'http://127.0.0.1:8015/health' },
  @{ Name = 'RadiologyReportFilling'; Wd = 'C:\Users\User\Desktop\AI-Services\RadiologyReportFilling'; Port = 8024; Health = 'http://127.0.0.1:8024/api/v1/health' },
  @{ Name = 'TemplateAutofill';       Wd = 'C:\Users\User\Desktop\AI-Services\MedicalImageTemplateAutofill'; Port = 8022; Health = 'http://127.0.0.1:8022/health' }
)

foreach ($s in $services) {
  Write-Host "Starting $($s.Name) ($($s.Port))..."
  $windowStyle = if ($Visible) { 'Normal' } else { 'Hidden' }
  Start-Process -FilePath python -ArgumentList 'main.py' -WorkingDirectory $s.Wd -WindowStyle $windowStyle | Out-Null
}

Write-Host ""
Write-Host "Workflow services and ports:"
foreach ($s in $services) {
  Write-Host " - $($s.Name): $($s.Port) [$($s.Health)]"
}
Write-Host ""
Write-Host "Started. Verify with: .\\check_services.ps1"
