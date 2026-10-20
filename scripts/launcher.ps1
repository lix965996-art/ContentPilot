param([ValidateSet('Start','Stop','Status')][string]$Action = 'Start', [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime-paths.ps1')
$paths = Get-ContentPilotPaths
$projectRoot = $paths.Project
$backend = Join-Path $projectRoot 'backend'
$frontend = Join-Path $projectRoot 'frontend'
$runtime = $paths.Run
$logs = $paths.Logs
$apiState = Join-Path $runtime 'api.json'
$webState = Join-Path $runtime 'web.json'
$legacyApiState = Join-Path $paths.LegacyRun 'api.json'
$legacyWebState = Join-Path $paths.LegacyRun 'web.json'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$node = if ($nodeCommand) { $nodeCommand.Source } else { $null }
$vite = Join-Path $frontend 'node_modules\vite\bin\vite.js'

function Read-State([string]$path) {
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try { return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json } catch { return $null }
}
function Get-TrackedProcess([string[]]$statePaths) {
  foreach ($path in $statePaths) {
    $state = Read-State $path
    if (-not $state) { continue }
    $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    if ($process.StartTime.ToUniversalTime().Ticks -ne [int64]$state.startTicks) { continue }
    return $process
  }
  return $null
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
  $api = Get-TrackedProcess @($apiState, $legacyApiState)
  $web = Get-TrackedProcess @($webState, $legacyWebState)
  $apiText = if($api -and (Test-Url 'http://127.0.0.1:8000/api/health')){"RUNNING (PID $($api.Id))"}else{'STOPPED'}
  $webText = if($web -and (Test-Url 'http://127.0.0.1:5173')){"RUNNING (PID $($web.Id))"}else{'STOPPED'}
  Write-Host "API : $apiText"
  Write-Host "Web : $webText"
  exit 0
}

if ($Action -eq 'Stop') {
  foreach($item in @(@($apiState,$legacyApiState,'API'),@($webState,$legacyWebState,'Web'))){
    $stopped = $false
    foreach ($statePath in @($item[0], $item[1])) {
      $process = Get-TrackedProcess @($statePath)
      if ($process) {
        Stop-ProcessTree $process.Id
        Write-Host "Stopped $($item[2]) (PID $($process.Id))"
        $stopped = $true
      }
      Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    }
    if (-not $stopped) { Write-Host "$($item[2]) is not running" }
  }
  exit 0
}

Set-ContentPilotPythonEnvironment $paths
New-Item -ItemType Directory -Force -Path $runtime,$logs | Out-Null

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

$existingApi = Get-TrackedProcess @($apiState, $legacyApiState)
if (-not $existingApi) {
  if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is already used by an untracked process.'
  }
  $api = Start-Process -FilePath $venvPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'api.log') -RedirectStandardError (Join-Path $logs 'api-error.log') -PassThru
  Save-State $apiState $api
  Write-Host "API started (PID $($api.Id))"
}

$existingWeb = Get-TrackedProcess @($webState, $legacyWebState)
if (-not $existingWeb) {
  if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 5173 is already used by an untracked process.'
  }
  $web = Start-Process -FilePath $node -ArgumentList @(('"' + $vite + '"'),'--host','127.0.0.1','--port','5173') -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'web.log') -RedirectStandardError (Join-Path $logs 'web-error.log') -PassThru
  Save-State $webState $web
  Write-Host "Web started (PID $($web.Id))"
}

if (-not (Wait-Url 'http://127.0.0.1:8000/api/health' 30)) { throw "API failed. See $(Join-Path $logs 'api-error.log')." }
if (-not (Wait-Url 'http://127.0.0.1:5173' 30)) { throw "Web failed. See $(Join-Path $logs 'web-error.log')." }
Write-Host 'ContentPilot is ready: http://127.0.0.1:5173' -ForegroundColor Green
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173' }
