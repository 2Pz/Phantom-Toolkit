#!/usr/bin/env bash
set -e

# =============================================================================
# Package Phantom Toolkit as an AppImage (Proton Wrapper)
# =============================================================================
#
# This script bundles the Windows executable (built previously) into an AppImage
# that runs via a bundled entry point script (AppRun) which invokes Proton.
#
# Requirements:
#   - dist/windows-X.X.X/ must exist (containing PhantomToolkit.exe)
#   - linuxdeploy must be available or will be downloaded
#   - AppRun (scripts/run_proton_phantomtoolkit.sh) must exist
# =============================================================================

# 1. Determine Version and Source
version=$(grep --max-count=1 '^version\s*=' pyproject.toml | cut -d '"' -f2)
windows_dist="dist/windows-$version"
linux_dist="dist/linux-$version"
app_dir="$linux_dist/AppDir"

if [ ! -d "$windows_dist" ]; then
    echo "Error: Windows distribution not found at $windows_dist"
    echo "Please run build-windows job first."
    exit 1
fi

echo "Packaging Phantom Toolkit v$version as AppImage..."

# 2. Prepare AppDir
rm -rf "$app_dir"
mkdir -p "$app_dir/usr/bin"
mkdir -p "$app_dir/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$app_dir/usr/share/applications"

# Copy Windows artifacts (the whole folder structure)
cp -r "$windows_dist"/* "$app_dir/usr/bin/"

# Build + bundle native host bridge for Linux dialogs/screenshot/sound.
# The Windows backend runs under Proton/Wine, so we need this helper on Linux.
if [ -f "phantom_backend/host_bridge.py" ]; then
    echo "Building native host bridge (PhantomHostBridge)..."
    if command -v uv >/dev/null 2>&1; then
        # Ensure dev deps exist (PyInstaller is a dev dependency).
        # In CI this is required because this packaging job doesn't install deps otherwise.
        uv sync --dev
        uv run python -m PyInstaller --noconfirm --clean \
            --name PhantomHostBridge \
            --onefile \
            --distpath "$linux_dist/bridge_dist" \
            --workpath "$linux_dist/bridge_build" \
            --specpath "$linux_dist/bridge_spec" \
            phantom_backend/host_bridge.py
    else
        # Fall back to system PyInstaller if available.
        python3 -m PyInstaller --noconfirm --clean \
            --name PhantomHostBridge \
            --onefile \
            --distpath "$linux_dist/bridge_dist" \
            --workpath "$linux_dist/bridge_build" \
            --specpath "$linux_dist/bridge_spec" \
            phantom_backend/host_bridge.py
    fi

    if [ -f "$linux_dist/bridge_dist/PhantomHostBridge" ]; then
        cp -f "$linux_dist/bridge_dist/PhantomHostBridge" "$app_dir/usr/bin/PhantomHostBridge"
        chmod +x "$app_dir/usr/bin/PhantomHostBridge" || true
    else
        echo "Warning: PhantomHostBridge build failed; dialogs/screenshots may not work under Proton." >&2
    fi
fi

# Copy Icon
icon_src="build/assets/phantom-toolkit.png"

if [ ! -f "$icon_src" ]; then
    echo "Generating icon..."
    if command -v uv >/dev/null 2>&1; then
        uv run python scripts/generate_icons.py
    else
        python3 scripts/generate_icons.py
    fi
fi

if [ -f "$icon_src" ]; then
    cp "$icon_src" "$app_dir/phantom-toolkit.png"
    cp "$icon_src" "$app_dir/usr/share/icons/hicolor/256x256/apps/phantom-toolkit.png"
else
    echo "Error: Icon not found and could not be generated."
    exit 1
fi

# Create Desktop File
cat > "$app_dir/usr/share/applications/phantom-toolkit.desktop" <<EOF
[Desktop Entry]
Name=Phantom Toolkit
Exec=AppRun
Icon=phantom-toolkit
Type=Application
Categories=Utility;
Comment=Elden Ring & Dark Souls III Toolkit (Proton)
EOF

# 3. Download linuxdeploy if needed
if [ ! -f "linuxdeploy-x86_64.AppImage" ]; then
    wget https://github.com/linuxdeploy/linuxdeploy/releases/download/1-alpha-20240109-1/linuxdeploy-x86_64.AppImage
    chmod +x linuxdeploy-x86_64.AppImage
fi

# 4. Build AppImage
export ARCH=x86_64
chmod +x scripts/run_proton_phantomtoolkit.sh
./linuxdeploy-x86_64.AppImage --appimage-extract-and-run \
    --appdir "$app_dir" \
    --output appimage \
    --desktop-file "$app_dir/usr/share/applications/phantom-toolkit.desktop" \
    --icon-file "$app_dir/phantom-toolkit.png" \
    --custom-apprun scripts/run_proton_phantomtoolkit.sh

# Move artifact
mkdir -p "$linux_dist"
mv Phantom_Toolkit*.AppImage "$linux_dist/PhantomToolkit.AppImage"

echo "AppImage created at $linux_dist/PhantomToolkit.AppImage"
