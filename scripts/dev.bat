@echo off
cd /d "%~dp0.."
echo Starting Phantom Backend...
start "Phantom Backend" cmd /k "uv run phantom-backend"

echo Starting Phantom Frontend...
cd gui
start "Phantom Frontend" cmd /k "npm run dev"
cd ..

echo Both services started!
