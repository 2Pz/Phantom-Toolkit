import os
import subprocess
import sys
from pathlib import Path


def main():
    # Define project root
    ROOT_DIR = Path(__file__).parent.parent.resolve()
    os.chdir(ROOT_DIR)

    print(f"[Build] Project Root: {ROOT_DIR}")

    # 1. Build Frontend
    print("[Build] Building Frontend...")
    gui_dir = ROOT_DIR / "gui"
    if not (gui_dir / "node_modules").exists():
        print("[Build] Installing GUI dependencies...")
        subprocess.check_call(["npm", "install"], cwd=gui_dir, shell=True)

    subprocess.check_call(["npm", "run", "build"], cwd=gui_dir, shell=True)

    # 2. Generate Icons
    print("[Build] Generating Icons...")
    icon_script = ROOT_DIR / "scripts" / "generate_icons.py"
    if icon_script.exists():
        subprocess.check_call([sys.executable, str(icon_script)])

    # 3. Operations for PyInstaller
    print("[Build] Running PyInstaller...")

    # Clean previous builds
    dist_dir = ROOT_DIR / "dist"
    build_dir = ROOT_DIR / "build"

    # We don't necessarily want to nuke 'dist' if it contains other things, but strictly for a clean build it's good.
    # checking if dist exists
    if not dist_dir.exists():
        dist_dir.mkdir()

    # Spec file location
    spec_file = ROOT_DIR / "packaging" / "PhantomToolkit.spec"

    if not spec_file.exists():
        print(f"[Error] Spec file not found at {spec_file}")
        sys.exit(1)

    # Get version for output directory
    import re

    pyproject = ROOT_DIR / "pyproject.toml"
    version = "0.0.0"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            version = match.group(1)

    print(f"[Build] Detected version: {version}")
    target_dist = dist_dir / f"windows-{version}"

    # Run PyInstaller
    cmd = [
        "uv",
        "run",
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(target_dist),
        "--workpath",
        str(build_dir),
        str(spec_file),
    ]

    print(f"[Build] Command: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    print(f"[Build] Done! Output in {target_dist}")


if __name__ == "__main__":
    main()
