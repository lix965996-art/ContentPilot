param([switch]$Force)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$version = 'v2.2.6'
$assetName = 'xiaohongshu-mcp-windows-amd64.exe'
$expectedSha256 = '16266FAC57D756D1811BD1A6FDC77226E268810296B355D942E1616839FB88E3'
$targetDirectory = Join-Path $projectRoot ".runtime\xiaohongshu-mcp\$version"
$targetPath = Join-Path $targetDirectory $assetName
$downloadUrl = "https://github.com/xpzouying/xiaohongshu-mcp/releases/download/$version/$assetName"

if ($env:OS -ne 'Windows_NT') {
  throw 'The bundled Xiaohongshu MCP installer currently supports Windows only.'
}

function Test-ExpectedHash([string]$path) {
  if (-not (Test-Path -LiteralPath $path)) { return $false }
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash -eq $expectedSha256
}

if (-not $Force -and (Test-ExpectedHash $targetPath)) {
  Write-Host "Xiaohongshu MCP is ready: $targetPath" -ForegroundColor Green
  exit 0
}

New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
$temporaryPath = "$targetPath.download"
Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue

Write-Host "Downloading Xiaohongshu MCP $version..." -ForegroundColor Cyan
try {
  Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $temporaryPath
  if (-not (Test-ExpectedHash $temporaryPath)) {
    throw 'Downloaded Xiaohongshu MCP checksum does not match the pinned release.'
  }
  Move-Item -LiteralPath $temporaryPath -Destination $targetPath -Force
} finally {
  Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
}

Write-Host 'Xiaohongshu MCP installed. ContentPilot will start it automatically when needed.' -ForegroundColor Green
