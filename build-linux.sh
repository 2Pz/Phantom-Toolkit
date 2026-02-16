#!/bin/sh

set -e

# Build Phantom Toolkit as a standalone (one-file) binary for Linux
#
# Usage with uv:
#     uv sync --dev
#     uv run ./build-linux.sh
#
# Notes:
# - PyInstaller does not cross-compile. This must run on Linux.
# - This script builds the frontend (gui/dist) then bundles it into the binary.

if [ "$(uname)" != Linux ]; then
	echo "This script only works on Linux."
	exit 1
fi

# Get version from pyproject.toml
version=$(grep --max-count=1 '^version\s*=' pyproject.toml | cut -d '"' -f2)

echo "Building frontend..."
cd gui

if [ -f package-lock.json ]; then
	npm ci
else
	npm install
fi

npm run build
cd -

echo "Generating placeholder icon..."
if command -v uv >/dev/null 2>&1; then
	uv run python scripts/generate_icons.py
else
	python3 scripts/generate_icons.py
fi

echo "Building with PyInstaller..."

distpath="dist/linux-$version"
mkdir -p "$distpath"

pyinstaller --clean --noconfirm \
	--name PhantomToolkit \
	--onefile \
	--windowed \
	--optimize 2 \
	--strip \
	--distpath "$distpath" \
	--add-data "gui/dist:gui_dist" \
	--add-data "phantom_backend/games:phantom_backend/games" \
	--collect-all phantom_backend \
	--hidden-import uvicorn \
	--hidden-import fastapi \
	--hidden-import engineio.async_drivers.asyncio \
	--hidden-import qtpy \
	--hidden-import PySide6 \
	--hidden-import PySide6.QtWebEngineWidgets \
	phantom_backend/main_desktop.py

echo "Linux build complete: $distpath/PhantomToolkit"
