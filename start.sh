#!/bin/bash
set -e

echo "[Phantom] Checking for node_modules..."
if [ ! -d "gui/node_modules" ]; then
    echo "[Phantom] Installing GUI dependencies..."
    cd gui
    npm install
    cd ..
fi

echo "[Phantom] Building GUI..."
cd gui
npm run build
cd ..

echo "[Phantom] Starting Desktop Client..."
# Ensure uv is in path
if command -v uv &> /dev/null; then
    uv run python -m phantom_backend.main_desktop
else
    echo "Error: 'uv' not found. Please install uv (https://docs.astral.sh/uv/)."
    exit 1
fi
