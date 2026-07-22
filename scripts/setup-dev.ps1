param([switch]$SkipFrontend)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $projectRoot 'backend'
$frontend = Join-Path $projectRoot 'frontend'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'

Write-Host 'ContentPilot first-time setup / dependency update' -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $venvPython)) {
  $pythonExe = $null
  $pythonArgs = @()
  $py = Get-Command py.exe -ErrorAction SilentlyContinue
  if ($py) {
    & $py.Source -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
      $pythonExe = $py.Source
      $pythonArgs = @('-3.12')
    }
  }
  if (-not $pythonExe) {
    foreach ($commandName in @('python.exe', 'python3.exe')) {
      $candidate = Get-Command $commandName -ErrorAction SilentlyContinue
      if (-not $candidate) { continue }
      & $candidate.Source -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) {
        $pythonExe = $candidate.Source
        break
      }
    }
  }
  if (-not $pythonExe) { throw 'Python 3.12 was not found. Install it or expose it through py/python.' }
  Write-Host '[1/5] Creating Python 3.12 virtual environment...'
  & $pythonExe @pythonArgs -m venv (Join-Path $backend '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}

Write-Host '[2/5] Syncing backend dependencies...'
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $backend 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }

if (-not $SkipFrontend) {
  if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) { throw 'Node.js 20+ was not found.' }
  Write-Host '[3/5] Syncing frontend dependencies...'
  Push-Location $frontend
  try { & npm.cmd install --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' } }
  finally { Pop-Location }
} else { Write-Host '[3/5] Frontend dependency sync skipped.' }

Write-Host '[4/5] Applying database migrations...'
Push-Location $backend
try { & $venvPython -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' } }
finally { Pop-Location }

Write-Host '[5/5] Seeding idempotent demo data...'
Push-Location $backend
try { & $venvPython -m app.db.seed; if ($LASTEXITCODE -ne 0) { throw 'Demo data seed failed.' } }
finally { Pop-Location }

$runtime = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
Set-Content -LiteralPath (Join-Path $runtime 'setup.complete') -Value (Get-Date -Format o) -Encoding UTF8
Write-Host 'Setup complete. Run .\contentpilot.ps1 start from the project root.' -ForegroundColor Green
