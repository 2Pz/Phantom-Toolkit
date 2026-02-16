#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build a Linux AppImage wrapper that launches PhantomToolkit.exe under Steam Proton.

Usage:
  packaging/build-appimage.sh --exe /path/to/PhantomToolkit.exe [--output /path/to/PhantomToolkit.AppImage]

Notes:
  - Requires appimagetool in PATH (either `appimagetool` or `appimagetool.AppImage`).
  - The resulting AppImage does NOT embed items/. Place an items/ folder next to the AppImage.
  - By default, this also builds a native Qt GUI wrapper (PySide6 + QtWebEngine) using PyInstaller.
    Disable with: PHANTOM_SKIP_QT_WRAPPER=1
EOF
}

exe=""
output=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --exe)
      exe="${2:-}"; shift 2;;
    --output)
      output="${2:-}"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2;;
  esac
done

if [[ -z "$exe" ]]; then
  usage
  exit 2
fi

if [[ ! -f "$exe" ]]; then
  echo "EXE not found: $exe" >&2
  exit 2
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template_dir="$root_dir/packaging/appimage/AppDir"

if [[ ! -d "$template_dir" ]]; then
  echo "Missing AppDir template: $template_dir" >&2
  exit 2
fi

appimagetool_bin=""
if command -v appimagetool >/dev/null 2>&1; then
  appimagetool_bin="appimagetool"
elif command -v appimagetool.AppImage >/dev/null 2>&1; then
  appimagetool_bin="appimagetool.AppImage"
else
  # CI-friendly fallback: use the vendored tools in this repo if present.
  vendored_dir="$root_dir/packaging/appimage"
  if [[ -x "$vendored_dir/appimagetool" ]]; then
    appimagetool_bin="$vendored_dir/appimagetool"
  elif [[ -x "$vendored_dir/appimagetool.AppImage" ]]; then
    appimagetool_bin="$vendored_dir/appimagetool.AppImage"
  fi
fi

if [[ -z "$appimagetool_bin" ]]; then
  echo "appimagetool not found in PATH." >&2
  echo "Install it (AppImageKit) or place appimagetool in PATH, then retry." >&2
  echo "Tip: this repo vendors appimagetool at packaging/appimage/." >&2
  exit 2
fi

# If appimagetool is itself an AppImage, prefer running it via extract-and-run.
# This avoids relying on FUSE availability on CI runners / restricted systems.
appimagetool_run=("$appimagetool_bin")
case "$appimagetool_bin" in
  *.AppImage|*.appimage)
    appimagetool_run+=("--appimage-extract-and-run")
    ;;
esac

arch="$(uname -m)"
version="$(python -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])' 2>/dev/null || echo "dev")"

if [[ -z "$output" ]]; then
  output="$root_dir/dist/PhantomToolkit-Proton-$version-$arch.AppImage"
fi

# appimagetool is executed from inside a build directory; ensure output is absolute
# so relative paths don't break.
if [[ "$output" != /* ]]; then
  output="$root_dir/$output"
fi

mkdir -p "$(dirname "$output")"

build_root="$root_dir/packaging/appimage/build"
rm -rf "$build_root"
mkdir -p "$build_root"

appdir="$build_root/AppDir"
cp -a "$template_dir" "$appdir"

# Bundle Windows exe
cp -f "$exe" "$appdir/PhantomToolkit.exe"

if [[ "${PHANTOM_SKIP_QT_WRAPPER:-0}" != "1" ]]; then
  echo "Building native Qt GUI wrapper (PyInstaller)..."
  wrapper_dist="$build_root/wrapper_dist"
  wrapper_build="$build_root/wrapper_build"
  wrapper_spec="$build_root/wrapper_spec"
  rm -rf "$wrapper_dist" "$wrapper_build" "$wrapper_spec"

  # Prefer project-managed environment (uv) so PyInstaller/dev deps resolve.
  py=()
  if command -v uv >/dev/null 2>&1; then
    py=(uv run python)
  elif command -v python3 >/dev/null 2>&1; then
    py=(python3)
  else
    py=(python)
  fi

  "${py[@]}" -m PyInstaller --noconfirm --clean \
    --name PhantomToolkitGui \
    --onefile \
    --distpath "$wrapper_dist" \
    --workpath "$wrapper_build" \
    --specpath "$wrapper_spec" \
    --hidden-import webview \
    --collect-all webview \
    --exclude-module PySide6 \
    --exclude-module PySide2 \
    --exclude-module PyQt5 \
    --exclude-module PyQt6 \
    --exclude-module qtpy \
    --exclude-module shiboken6 \
    --exclude-module shiboken2 \
    "$root_dir/phantom_backend/qt_gui_wrapper.py"

  if [[ ! -f "$wrapper_dist/PhantomToolkitGui" ]]; then
    echo "Failed to build PhantomToolkitGui wrapper binary." >&2
    echo "Tip: run 'uv sync --dev' (PyInstaller is a dev dependency)." >&2
    exit 2
  fi
  cp -f "$wrapper_dist/PhantomToolkitGui" "$appdir/PhantomToolkitGui"
  chmod +x "$appdir/PhantomToolkitGui" || true
fi

if [[ "${PHANTOM_SKIP_HOST_BRIDGE:-0}" != "1" ]]; then
  echo "Building native host bridge (PyInstaller)..."
  bridge_dist="$build_root/bridge_dist"
  bridge_build="$build_root/bridge_build"
  bridge_spec="$build_root/bridge_spec"
  rm -rf "$bridge_dist" "$bridge_build" "$bridge_spec"

  # Prefer project-managed environment (uv) so PyInstaller/dev deps resolve.
  py=()
  if command -v uv >/dev/null 2>&1; then
    py=(uv run python)
  elif command -v python3 >/dev/null 2>&1; then
    py=(python3)
  else
    py=(python)
  fi

  "${py[@]}" -m PyInstaller --noconfirm --clean \
    --name PhantomHostBridge \
    --onefile \
    --distpath "$bridge_dist" \
    --workpath "$bridge_build" \
    --specpath "$bridge_spec" \
    "$root_dir/phantom_backend/host_bridge.py"

  if [[ ! -f "$bridge_dist/PhantomHostBridge" ]]; then
    echo "Failed to build PhantomHostBridge binary." >&2
    echo "Tip: run 'uv sync --dev' (PyInstaller is a dev dependency)." >&2
    exit 2
  fi
  cp -f "$bridge_dist/PhantomHostBridge" "$appdir/PhantomHostBridge"
  chmod +x "$appdir/PhantomHostBridge" || true
else
  echo "Skipping host bridge build (PHANTOM_SKIP_HOST_BRIDGE=1)"
fi

echo "Building AppImage..."
echo "  Template: $template_dir"
echo "  EXE:      $exe"
echo "  Output:   $output"
echo ""

(
  cd "$build_root"
  # Use an absolute path because appimagetool's AppRun can change cwd internally.
  ARCH="$arch" "${appimagetool_run[@]}" "$appdir" "$output"
)

chmod +x "$output" || true
echo ""
echo "Done: $output"

