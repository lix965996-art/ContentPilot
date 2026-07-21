@echo off
setlocal
cd /d "%~dp0.."

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Backend environment is missing. Run scripts\start-dev.bat first.
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo [ERROR] Frontend dependencies are missing. Run scripts\start-dev.bat first.
  exit /b 1
)

echo [1/6] Backend lint...
pushd backend
".venv\Scripts\python.exe" -m ruff check app alembic || (popd & exit /b 1)
".venv\Scripts\python.exe" -m ruff format --check app alembic || (popd & exit /b 1)

echo [2/6] Backend tests...
".venv\Scripts\python.exe" -m pytest || (popd & exit /b 1)
popd

echo [3/6] Frontend format and lint...
pushd frontend
call npm run format:check || (popd & exit /b 1)
call npm run lint || (popd & exit /b 1)

echo [4/6] Frontend type check and production build...
call npm run build || (popd & exit /b 1)

echo [5/6] Frontend unit tests...
call npm run test:run || (popd & exit /b 1)

echo [6/6] Login and RBAC browser tests...
call npm run test:e2e || (popd & exit /b 1)
popd

echo [OK] All checks passed.
exit /b 0

