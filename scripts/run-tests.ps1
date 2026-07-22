$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $projectRoot 'backend'
$frontend = Join-Path $projectRoot 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
  throw 'Backend environment is missing. Run .\contentpilot.ps1 setup first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules'))) {
  throw 'Frontend dependencies are missing. Run .\contentpilot.ps1 setup first.'
}

function Invoke-Checked([scriptblock]$Command, [string]$FailureMessage) {
  & $Command
  if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

Write-Host '[1/6] Backend lint...' -ForegroundColor Cyan
Push-Location $backend
try {
  Invoke-Checked { & $python -m ruff check app alembic } 'Backend lint failed.'
  Invoke-Checked { & $python -m ruff format --check app alembic } 'Backend format check failed.'

  Write-Host '[2/6] Backend tests...' -ForegroundColor Cyan
  Invoke-Checked { & $python -m pytest } 'Backend tests failed.'
} finally {
  Pop-Location
}

Push-Location $frontend
try {
  Write-Host '[3/6] Frontend format and lint...' -ForegroundColor Cyan
  Invoke-Checked { & npm.cmd run format:check } 'Frontend format check failed.'
  Invoke-Checked { & npm.cmd run lint } 'Frontend lint failed.'

  Write-Host '[4/6] Frontend type check and production build...' -ForegroundColor Cyan
  Invoke-Checked { & npm.cmd run build } 'Frontend build failed.'

  Write-Host '[5/6] Frontend unit tests...' -ForegroundColor Cyan
  Invoke-Checked { & npm.cmd run test:run } 'Frontend unit tests failed.'

  Write-Host '[6/6] Browser tests...' -ForegroundColor Cyan
  Invoke-Checked { & npm.cmd run test:e2e } 'Browser tests failed.'
} finally {
  Pop-Location
}

Write-Host '[OK] All checks passed.' -ForegroundColor Green
