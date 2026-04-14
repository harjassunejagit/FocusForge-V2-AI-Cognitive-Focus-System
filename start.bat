@echo off
title FocusForge AI v2 — Launcher
color 0A

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║        ⚡ FocusForge AI v2 — Starting        ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ── Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ❌ Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: ── Check Node ────────────────────────────────────────────────────────────
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ❌ Node.js not found. Install from https://nodejs.org
    pause
    exit /b 1
)

:: ── Install Python deps if needed ─────────────────────────────────────────
echo  [1/3] Checking Python dependencies...
pip show fastapi >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing Python packages...
    pip install -r requirements.txt
)

:: ── Install Node deps if needed ───────────────────────────────────────────
echo  [2/3] Checking Node dependencies...
if not exist "dashboard\node_modules" (
    echo  Installing Node packages...
    cd dashboard && npm install && cd ..
)

:: ── Start Backend ─────────────────────────────────────────────────────────
echo  [3/3] Starting services...
echo.
echo  Backend  →  http://localhost:8765
echo  Frontend →  http://localhost:3000  (opens in 4 seconds)
echo.
start "FocusForge Backend" cmd /k "python run.py --open-browser"
timeout /t 3 /nobreak >nul

:: ── Start Frontend ────────────────────────────────────────────────────────
start "FocusForge Dashboard" cmd /k "cd dashboard && npm run dev"
timeout /t 4 /nobreak >nul

:: ── Open Browser ──────────────────────────────────────────────────────────
start http://localhost:3000

echo  ✅ Both services started!
echo  📊 Dashboard: http://localhost:3000
echo.
echo  To stop: close the two terminal windows that opened.
echo.
pause
