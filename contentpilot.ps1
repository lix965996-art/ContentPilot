param(
  [Parameter(Position = 0)]
  [ValidateSet('start', 'stop', 'status', 'setup', 'logs', 'test', 'db')]
  [string]$Action = 'start',
  [switch]$NoBrowser,
  [switch]$Follow
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$scripts = Join-Path $projectRoot 'scripts'

switch ($Action) {
  'start' {
    & (Join-Path $scripts 'launcher.ps1') -Action Start -NoBrowser:$NoBrowser
  }
  'stop' {
    & (Join-Path $scripts 'launcher.ps1') -Action Stop
  }
  'status' {
    & (Join-Path $scripts 'launcher.ps1') -Action Status
  }
  'setup' {
    & (Join-Path $scripts 'setup-dev.ps1')
  }
  'test' {
    & (Join-Path $scripts 'run-tests.ps1')
  }
  'db' {
    & (Join-Path $scripts 'init-db.ps1')
  }
  'logs' {
    $logFiles = @(
      (Join-Path $projectRoot 'logs\api.log'),
      (Join-Path $projectRoot 'logs\api-error.log'),
      (Join-Path $projectRoot 'logs\web.log'),
      (Join-Path $projectRoot 'logs\web-error.log')
    ) | Where-Object { Test-Path -LiteralPath $_ }
    if (-not $logFiles) {
      Write-Host 'No local runtime logs exist yet. Start ContentPilot first.' -ForegroundColor Yellow
      exit 0
    }
    if ($Follow) {
      Write-Host 'Following logs. Press Ctrl+C to stop.' -ForegroundColor Cyan
      Get-Content -LiteralPath $logFiles -Tail 80 -Wait
    } else {
      Get-Content -LiteralPath $logFiles -Tail 80
    }
  }
}
