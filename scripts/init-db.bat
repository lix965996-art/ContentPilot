@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not defined MYSQL_HOST set "MYSQL_HOST=127.0.0.1"
if not defined MYSQL_PORT set "MYSQL_PORT=3306"
if not defined MYSQL_USER set "MYSQL_USER=root"
if not defined MYSQL_PASSWORD set "MYSQL_PASSWORD=123456"

set "MYSQL_EXE=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"
if not exist "%MYSQL_EXE%" (
  where mysql.exe >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] MySQL 8 client was not found. Install MySQL 8 or add mysql.exe to PATH.
    exit /b 1
  )
  set "MYSQL_EXE=mysql.exe"
)

sc query MySQL80 | findstr /I "RUNNING" >nul
if errorlevel 1 (
  echo [ERROR] MySQL80 service is not running. Start it in Windows Services first.
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] backend\.venv does not exist. Run scripts\start-dev.bat first.
  exit /b 1
)

echo [1/3] Creating the socialflow database if needed...
set "MYSQL_PWD=%MYSQL_PASSWORD%"
"%MYSQL_EXE%" --user=%MYSQL_USER% --host=%MYSQL_HOST% --port=%MYSQL_PORT% --protocol=TCP --execute="CREATE DATABASE IF NOT EXISTS socialflow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
if errorlevel 1 (
  set "MYSQL_PWD="
  echo [ERROR] Could not connect to MySQL. Check MYSQL_USER and MYSQL_PASSWORD.
  exit /b 1
)
set "MYSQL_PWD="

echo [2/3] Applying Alembic migrations...
pushd backend
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
  popd
  exit /b 1
)

echo [3/3] Seeding roles and demo accounts...
".venv\Scripts\python.exe" -m app.db.seed
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" exit /b %EXIT_CODE%

echo [OK] Database, roles, and demo accounts are ready.
exit /b 0
