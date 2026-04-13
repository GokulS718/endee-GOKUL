@echo off
setlocal EnableDelayedExpansion
echo.
echo ████████████████████████████████████████████████████████████
echo  AI Fake News Detector v3.0 — Full Stack Startup
echo ████████████████████████████████████████████████████████████
echo.

:: ── Step 1: Start Endee Vector DB via Docker ──────────────────────────────────
echo [1/4] Starting Endee Vector Database (Docker on port 8080)...

:: Check if Docker is running
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo   ⚠  Docker Desktop is NOT running!
    echo   Please start Docker Desktop and then run this script again.
    echo   Download: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

:: Check if endee-server container exists
docker inspect endee-server >nul 2>&1
if %ERRORLEVEL% equ 0 (
    :: Container exists — start it if stopped
    docker start endee-server >nul 2>&1
    echo   ✓ Endee server started (existing container).
) else (
    :: Container does not exist — create and run it
    echo   Creating Endee Docker container (first time — pulling image ~200MB)...
    if not exist "%~dp0endee-data" mkdir "%~dp0endee-data"
    docker run -d ^
        -p 8080:8080 ^
        -v "%~dp0endee-data:/data" ^
        --name endee-server ^
        --restart unless-stopped ^
        endeeio/endee-server:latest
    if %ERRORLEVEL% neq 0 (
        echo   ERROR: Failed to start Endee Docker container.
        pause
        exit /b 1
    )
    echo   ✓ Endee server container created and started.
)

echo   Waiting for Endee to be ready on port 8080...
set /a tries=0
:WAIT_ENDEE
set /a tries+=1
if !tries! gtr 30 (
    echo   ⚠  Endee did not become ready in time. Continuing anyway...
    goto ENDEE_DONE
)
curl -s http://localhost:8080 >nul 2>&1
if %ERRORLEVEL% neq 0 (
    timeout /t 2 /nobreak >nul
    goto WAIT_ENDEE
)
echo   ✓ Endee is ready at http://localhost:8080
:ENDEE_DONE

:: ── Step 2: Backend Python Setup ──────────────────────────────────────────────
echo.
echo [2/4] Setting up Backend (FastAPI on port 8000)...
cd /d "%~dp0backend"

if not exist "venv" (
    echo   Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo   ERROR: Failed to create venv. Ensure Python 3.8+ is installed.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

echo   Installing / updating Python dependencies...
pip install -r requirements.txt --quiet --upgrade
if errorlevel 1 (
    echo   WARNING: Some packages may have failed to install. Continuing...
)

:: ── Step 3: Seed Endee DB if needed ──────────────────────────────────────────
echo.
echo [3/4] Checking Endee database seed status...

:: Check if already seeded by querying the API (endee must be running)
echo   Seeding Endee DB with HuggingFace + GitHub datasets...
echo   (This may take 5-10 minutes on first run — downloading ~90MB model + datasets)
echo   You can monitor progress in the terminal window that will open.
echo.
start cmd /k "title Endee DB Seeder && cd /d %~dp0backend && call venv\Scripts\activate.bat && python seed_endee.py --source all && echo. && echo ✅ Seeding complete! You can close this window. && pause"

:: Give it a moment to start
timeout /t 3 /nobreak >nul

:: ── Step 4: Start FastAPI Backend ─────────────────────────────────────────────
echo.
echo [4/4] Starting FastAPI and Frontend servers...

start cmd /k "title Backend — FastAPI (port 8000) && cd /d %~dp0backend && call venv\Scripts\activate.bat && uvicorn main:app --host 127.0.0.1 --port 8000 --reload"

:: ── Step 5: Start Frontend ────────────────────────────────────────────────────
cd /d "%~dp0frontend"

echo   Installing Node dependencies (first-run only)...
call npm install --prefer-offline 2>nul || npm install

echo   Starting Vite dev server on port 5173...
start cmd /k "title Frontend — Vite (port 5173) && cd /d %~dp0frontend && npm run dev"

cd /d "%~dp0"

:: ── Summary ───────────────────────────────────────────────────────────────────
echo.
echo ████████████████████████████████████████████████████████████
echo  All services launching in separate windows!
echo.
echo  🔍 Frontend      : http://localhost:5173
echo  ⚡ Backend API   : http://127.0.0.1:8000
echo  📖 API Docs      : http://127.0.0.1:8000/docs
echo  🗄  Endee DB      : http://localhost:8080
echo  📊 Seed Status   : http://127.0.0.1:8000/api/seed-status
echo  ❤  Health Check  : http://127.0.0.1:8000/api/health
echo.
echo  NOTE: The seeder window will run in the background.
echo  The backend works immediately — the more vectors seeded,
echo  the better the fact-checking accuracy gets over time.
echo ████████████████████████████████████████████████████████████
echo.
pause
