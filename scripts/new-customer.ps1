# Creates an isolated ContentPilot deployment folder for one customer.
# Each customer gets an independent Docker Compose project: own database volume,
# own uploads volume, own ports and freshly generated secrets.
#
# Usage:
#   .\scripts\new-customer.ps1 -Name acme -Port 8081 -ApiPort 8001
#   cd ..\contentpilot-customers\acme
#   docker compose up -d --build

param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[a-z0-9][a-z0-9-]{1,30}$')]
  [string]$Name,
  [Parameter(Mandatory = $true)]
  [ValidateRange(1024, 65535)]
  [int]$Port,
  [Parameter(Mandatory = $true)]
  [ValidateRange(1024, 65535)]
  [int]$ApiPort,
  [string]$OutputRoot = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $OutputRoot) {
  $OutputRoot = Join-Path (Split-Path $repoRoot -Parent) 'contentpilot-customers'
}
$customerDir = Join-Path $OutputRoot $Name

if ($Port -eq $ApiPort) { throw 'Port and ApiPort must differ.' }
if (Test-Path -LiteralPath $customerDir) {
  throw "Customer folder already exists: $customerDir. Pick another name or remove it manually."
}

function New-RandomSecret([int]$bytes = 48) {
  $buffer = [byte[]]::new($bytes)
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
  # URL-safe so the value works inside the MySQL connection string too.
  return ([Convert]::ToBase64String($buffer)).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

function New-InitialPassword {
  # Element Plus form and backend both require letters + digits; add one symbol for strength.
  $secret = New-RandomSecret 12
  return "Cp$secret!9"
}

New-Item -ItemType Directory -Force -Path $customerDir | Out-Null

$adminPassword = New-InitialPassword
$envLines = @(
  "# ContentPilot customer deployment: $Name"
  "# Generated $(Get-Date -Format 'yyyy-MM-dd HH:mm') by scripts/new-customer.ps1"
  "COMPOSE_PROJECT_NAME=contentpilot-$Name"
  "CONTENTPILOT_PORT=$Port"
  "CONTENTPILOT_API_PORT=$ApiPort"
  ''
  "MYSQL_PASSWORD=$(New-RandomSecret 24)"
  "MYSQL_ROOT_PASSWORD=$(New-RandomSecret 24)"
  "JWT_SECRET=$(New-RandomSecret 48)"
  "PLATFORM_CREDENTIAL_KEY=$(New-RandomSecret 48)"
  ''
  '# Customer deployments stay clean and closed by default.'
  'APP_DEMO_MODE=false'
  'ALLOW_REGISTRATION=false'
  "ADMIN_INITIAL_PASSWORD=$adminPassword"
  ''
  'MEDIA_FALLBACK_ENABLED=true'
  'PUBLISH_MODE=manual'
  'EXPERIMENTAL_BROWSER_PUBLISHING_ENABLED=false'
  'WECHATSYNC_CLI_ENABLED=false'
  ''
  '# Model service is usually configured later in the admin UI.'
  'LLM_PROVIDER=openai-compatible'
  'LLM_BASE_URL='
  'LLM_API_KEY='
  'LLM_MODEL='
  'UNSPLASH_ACCESS_KEY='
)
Set-Content -LiteralPath (Join-Path $customerDir '.env') -Value ($envLines -join "`n") -Encoding UTF8 -NoNewline

# The compose file lives in the repo; each customer folder only carries its .env.
$composeSource = Join-Path $repoRoot 'compose.yaml'
$startLines = @(
  '# Start/upgrade this customer instance. Run from this folder.'
  "docker compose -f `"$composeSource`" --env-file .env up -d --build"
)
Set-Content -LiteralPath (Join-Path $customerDir 'start.ps1') -Value ($startLines -join "`n") -Encoding UTF8

Write-Host ''
Write-Host "Customer '$Name' prepared at: $customerDir" -ForegroundColor Green
Write-Host "  Web  : http://127.0.0.1:$Port"
Write-Host "  API  : http://127.0.0.1:$ApiPort"
Write-Host "  Admin: admin / $adminPassword" -ForegroundColor Yellow
Write-Host ''
Write-Host 'Next steps:' -ForegroundColor Cyan
Write-Host "  1. cd `"$customerDir`""
Write-Host '  2. .\start.ps1'
Write-Host '  3. Deliver the admin password to the customer over a secure channel,'
Write-Host '     and ask them to change it after first login.'
Write-Host ''
Write-Host 'Registration is closed for this instance; the admin creates operator accounts in the UI.'
