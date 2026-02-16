#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Prepare artifacts for release upload
# =============================================================================

VERSION="$1"
DIST_DIR="dist"
ARTIFACTS_DIR="artifacts"

echo "Preparing artifacts for $VERSION..."

# Ensure dist exists
mkdir -p "$DIST_DIR"

# 1. Linux AppImage
# Should already be a single file
cp "$ARTIFACTS_DIR/phantom-toolkit-linux/PhantomToolkit.AppImage" "$DIST_DIR/Phantom_Toolkit-${VERSION}-x86_64.AppImage"

# 2. Windows Executable
# The artifact is a single exe (onefile build)
if [ -f "$ARTIFACTS_DIR/phantom-toolkit-windows/PhantomToolkit.exe" ]; then
    cp "$ARTIFACTS_DIR/phantom-toolkit-windows/PhantomToolkit.exe" "$DIST_DIR/PhantomToolkit-${VERSION}.exe"
else
    echo "Warning: Windows EXE not found in artifacts."
fi

ls -lh "$DIST_DIR"
