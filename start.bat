@echo off
setlocal

echo [Phantom] Checking for node_modules...
if not exist "gui\node_modules" (
    echo [Phantom] Installing GUI dependencies...
    cd gui
    call npm install
    cd ..
)

echo [Phantom] Building GUI...
cd gui
call npm run build
if %errorlevel% neq 0 (
    echo [Phantom] GUI build failed!
    pause
    exit /b %errorlevel%
)
cd ..

echo [Phantom] Starting Desktop Client...
uv run python -m phantom_backend.main_desktop
if %errorlevel% neq 0 (
    echo [Phantom] Application exited with error.
    pause
)

endlocal
