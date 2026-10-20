$script:ContentPilotProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Get-ContentPilotPaths {
  $configuredVar = ([string]$env:CONTENTPILOT_VAR_DIR).Trim()
  $varDirectory = if ([string]::IsNullOrWhiteSpace($configuredVar)) {
    Join-Path $script:ContentPilotProjectRoot 'var'
  } elseif ([System.IO.Path]::IsPathRooted($configuredVar)) {
    $configuredVar
  } else {
    Join-Path $script:ContentPilotProjectRoot $configuredVar
  }
  $varDirectory = [System.IO.Path]::GetFullPath($varDirectory)

  return [pscustomobject]@{
    Project = $script:ContentPilotProjectRoot
    Var = $varDirectory
    Run = Join-Path $varDirectory 'run'
    Logs = Join-Path $varDirectory 'logs'
    Uploads = Join-Path $varDirectory 'uploads'
    Sessions = Join-Path $varDirectory 'sessions'
    Tools = Join-Path $varDirectory 'tools'
    Cache = Join-Path $varDirectory 'cache'
    Reports = Join-Path $varDirectory 'reports'
    Deployments = Join-Path $varDirectory 'deployments'
    LegacyRun = Join-Path $script:ContentPilotProjectRoot '.runtime'
  }
}

function Set-ContentPilotPythonEnvironment($Paths) {
  $env:CONTENTPILOT_VAR_DIR = $Paths.Var
  $env:PYTHONDONTWRITEBYTECODE = '1'
}
