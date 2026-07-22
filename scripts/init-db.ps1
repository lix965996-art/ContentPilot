$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $projectRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$mysqlHost = if ($env:MYSQL_HOST) { $env:MYSQL_HOST } else { '127.0.0.1' }
$mysqlPort = if ($env:MYSQL_PORT) { $env:MYSQL_PORT } else { '3306' }
$mysqlUser = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { 'root' }
$mysqlPassword = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { '123456' }
$defaultMysql = 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe'
$mysql = if (Test-Path -LiteralPath $defaultMysql) {
  $defaultMysql
} else {
  (Get-Command mysql.exe -ErrorAction Stop).Source
}

if (-not (Test-Path -LiteralPath $python)) {
  throw 'Backend environment is missing. Run .\contentpilot.ps1 setup first.'
}

Write-Host '[1/3] Creating the content database if needed...' -ForegroundColor Cyan
$env:MYSQL_PWD = $mysqlPassword
try {
  & $mysql --user=$mysqlUser --host=$mysqlHost --port=$mysqlPort --protocol=TCP `
    --execute='CREATE DATABASE IF NOT EXISTS socialflow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'
  if ($LASTEXITCODE -ne 0) { throw 'Could not connect to MySQL.' }
} finally {
  Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
}

Push-Location $backend
try {
  Write-Host '[2/3] Applying Alembic migrations...' -ForegroundColor Cyan
  & $python -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }

  Write-Host '[3/3] Seeding roles and initial accounts...' -ForegroundColor Cyan
  & $python -m app.db.seed
  if ($LASTEXITCODE -ne 0) { throw 'Database seed failed.' }
} finally {
  Pop-Location
}

Write-Host '[OK] Database is ready.' -ForegroundColor Green
