param([ValidateSet('Start','Stop','Status')][string]$Action = 'Start', [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $projectRoot 'backend'
$frontend = Join-Path $projectRoot 'frontend'
$runtime = Join-Path $projectRoot '.runtime'
$logs = Join-Path $projectRoot 'logs'
$apiState = Join-Path $runtime 'api.json'
$webState = Join-Path $runtime 'web.json'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$node = if ($nodeCommand) { $nodeCommand.Source } else { $null }
$vite = Join-Path $frontend 'node_modules\vite\bin\vite.js'
New-Item -ItemType Directory -Force -Path $runtime,$logs | Out-Null

function Read-State([string]$path) {
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try { return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json } catch { return $null }
}
function Get-TrackedProcess([string]$path) {
  $state = Read-State $path
  if (-not $state) { return $null }
  $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
  if (-not $process) { return $null }
  if ($process.StartTime.ToUniversalTime().Ticks -ne [int64]$state.startTicks) { return $null }
  return $process
}
function Save-State([string]$path, $process) {
  @{ pid=$process.Id; startTicks=$process.StartTime.ToUniversalTime().Ticks } |
    ConvertTo-Json | Set-Content -LiteralPath $path -Encoding UTF8
}
function Stop-ProcessTree([int]$processId) {
  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction SilentlyContinue
  foreach($child in $children){ Stop-ProcessTree ([int]$child.ProcessId) }
  Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}
function Test-Url([string]$url) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
    return $response.StatusCode -eq 200
  } catch { return $false }
}
function Wait-Url([string]$url,[int]$seconds) {
  $deadline=(Get-Date).AddSeconds($seconds)
  while((Get-Date) -lt $deadline){
    if(Test-Url $url){return $true}
    Start-Sleep -Milliseconds 500
  }
  return $false
}

if ($Action -eq 'Status') {
  $api = Get-TrackedProcess $apiState
  $web = Get-TrackedProcess $webState
  $apiText = if($api -and (Test-Url 'http://127.0.0.1:8000/api/health')){"RUNNING (PID $($api.Id))"}else{'STOPPED'}
  $webText = if($web -and (Test-Url 'http://127.0.0.1:5173')){"RUNNING (PID $($web.Id))"}else{'STOPPED'}
  Write-Host "API : $apiText"
  Write-Host "Web : $webText"
  exit 0
}

if ($Action -eq 'Stop') {
  foreach($item in @(@($apiState,'API'),@($webState,'Web'))){
    $process=Get-TrackedProcess $item[0]
    if($process){ Stop-ProcessTree $process.Id; Write-Host "Stopped $($item[1]) (PID $($process.Id))" }
    else { Write-Host "$($item[1]) is not running" }
    Remove-Item -LiteralPath $item[0] -Force -ErrorAction SilentlyContinue
  }
  exit 0
}

if (-not (Test-Path -LiteralPath $venvPython) -or -not (Test-Path -LiteralPath $vite)) {
  Write-Host 'Dependencies are missing. Running first-time setup...' -ForegroundColor Yellow
  & (Join-Path $PSScriptRoot 'setup-dev.ps1')
}
if (-not $node) { throw 'Node.js was not found.' }

Push-Location $backend
try {
  & $venvPython -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
} finally {
  Pop-Location
}

$existingApi = Get-TrackedProcess $apiState
if (-not $existingApi) {
  if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is already used by an untracked process.'
  }
  $api = Start-Process -FilePath $venvPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'api.log') -RedirectStandardError (Join-Path $logs 'api-error.log') -PassThru
  Save-State $apiState $api
  Write-Host "API started (PID $($api.Id))"
}

$existingWeb = Get-TrackedProcess $webState
if (-not $existingWeb) {
  if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 5173 is already used by an untracked process.'
  }
  $web = Start-Process -FilePath $node -ArgumentList @($vite,'--host','127.0.0.1','--port','5173') -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'web.log') -RedirectStandardError (Join-Path $logs 'web-error.log') -PassThru
  Save-State $webState $web
  Write-Host "Web started (PID $($web.Id))"
}

if (-not (Wait-Url 'http://127.0.0.1:8000/api/health' 30)) { throw 'API failed. See logs\api-error.log.' }
if (-not (Wait-Url 'http://127.0.0.1:5173' 30)) { throw 'Web failed. See logs\web-error.log.' }
Write-Host 'ContentPilot is ready: http://127.0.0.1:5173' -ForegroundColor Green
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173' }
