$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime-paths.ps1')
$paths = Get-ContentPilotPaths
Set-ContentPilotPythonEnvironment $paths
$projectRoot = $paths.Project
$backend = Join-Path $projectRoot 'backend'
$frontend = Join-Path $projectRoot 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$ruffCache = Join-Path $paths.Cache 'ruff'
$pytestCache = Join-Path $paths.Cache 'pytest'
$pytestTemporary = Join-Path $paths.Cache 'pytest-tmp'
$coverageDirectory = Join-Path $paths.Reports 'coverage'
$coverageFile = Join-Path $coverageDirectory 'backend.json'
New-Item -ItemType Directory -Force -Path $coverageDirectory | Out-Null

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

Write-Host '[1/6] Backend lint and type check...' -ForegroundColor Cyan
Push-Location $backend
try {
  Invoke-Checked { & $python -m ruff check --cache-dir $ruffCache app alembic } 'Backend lint failed.'
  Invoke-Checked { & $python -m ruff format --cache-dir $ruffCache --check app alembic } 'Backend format check failed.'
  Invoke-Checked { & $python -m pyright -p pyrightconfig.json --pythonpath $python } 'Backend type check failed.'
  Invoke-Checked { & (Join-Path $backend '.venv\Scripts\lint-imports.exe') } 'Backend architecture contracts failed.'

  Write-Host '[2/6] Backend tests with coverage...' -ForegroundColor Cyan
  Invoke-Checked { & $python -m pytest -o "cache_dir=$pytestCache" "--basetemp=$pytestTemporary" --cov=app --cov-branch --cov-report=term --cov-report="json:$coverageFile" } 'Backend tests failed.'
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
  Invoke-Checked { & npm.cmd exec -- playwright install chromium } 'Browser test dependency installation failed.'
  Invoke-Checked { & npm.cmd run test:e2e } 'Browser tests failed.'
} finally {
  Pop-Location
}

Write-Host '[OK] All checks passed.' -ForegroundColor Green
