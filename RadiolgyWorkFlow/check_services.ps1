param(
  [int]$TimeoutSeconds = 5
)

$ErrorActionPreference = 'Stop'

$checks = @(
  @{ Name = 'RadiologyImageQaAI';     Url = 'http://127.0.0.1:8016/health' },
  @{ Name = 'InterpretationAssist';   Url = 'http://127.0.0.1:8015/health' },
  @{ Name = 'RadiologyReportFilling'; Url = 'http://127.0.0.1:8024/api/v1/health' },
  @{ Name = 'TemplateAutofill';       Url = 'http://127.0.0.1:8022/health' }
)

foreach ($c in $checks) {
  Write-Host "== $($c.Name) =="
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $c.Url -TimeoutSec $TimeoutSeconds
    Write-Host "OK  $($r.StatusCode)  $($r.Content)"
  } catch {
    Write-Host "ERR $($_.Exception.Message)"
  }
  Write-Host ""
}
