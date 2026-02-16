#!/usr/bin/env python3
"""Sync the project version across all version files.

This is a convenience script for local development.  In CI, release-please
handles version bumps automatically via x-release-please-version annotations.

Usage:
    # Sync from pyproject.toml -> other files
    python scripts/sync_version.py

    # Set a new version and update all files
    python scripts/sync_version.py --set 0.1.0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
VERSION_FILE = ROOT / "packaging" / "version_file.txt"
MANIFEST = ROOT / ".release-please-manifest.json"

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def get_version() -> str:
    """Read the version string from pyproject.toml."""
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        print("ERROR: Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def set_pyproject_version(ver: str) -> None:
    """Update pyproject.toml version = \"...\"."""
    text = PYPROJECT.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{ver}"',
        text,
        flags=re.MULTILINE,
    )
    if n != 1:
        print("ERROR: Could not update version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    PYPROJECT.write_text(new_text, encoding="utf-8")


def version_tuple(ver: str) -> str:
    """Convert '1.2.3' → '(1, 2, 3, 0)'."""
    parts = ver.split(".")
    while len(parts) < 4:
        parts.append("0")
    return f"({', '.join(parts)})"


def sync(ver: str) -> None:
    """Update packaging/version_file.txt with the given version string."""
    content = VERSION_FILE.read_text(encoding="utf-8")
    vtuple = version_tuple(ver)

    # Replace filevers / prodvers tuples
    content = re.sub(
        r"(filevers=)\([^)]+\)",
        rf"\g<1>{vtuple}",
        content,
    )
    content = re.sub(
        r"(prodvers=)\([^)]+\)",
        rf"\g<1>{vtuple}",
        content,
    )
    # Replace FileVersion / ProductVersion strings
    content = re.sub(
        r"(StringStruct\(u'FileVersion',\s*u')[^']+(')",
        rf"\g<1>{ver}\2",
        content,
    )
    content = re.sub(
        r"(StringStruct\(u'ProductVersion',\s*u')[^']+(')",
        rf"\g<1>{ver}\2",
        content,
    )

    VERSION_FILE.write_text(content, encoding="utf-8")
    print(f"Synced packaging/version_file.txt -> {ver}")


def sync_manifest(ver: str) -> None:
    """Update .release-please-manifest.json with the given version."""
    data = {".": ver}
    MANIFEST.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    print(f"Synced .release-please-manifest.json -> {ver}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync Phantom Toolkit version files.")
    p.add_argument(
        "--set",
        dest="set_version",
        metavar="X.Y.Z",
        help="Set pyproject.toml to this version, then sync other version files.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change, but do not write files.",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.set_version:
        ver = args.set_version.strip()
        if not _SEMVER_RE.match(ver):
            print("ERROR: --set must be like X.Y.Z (example: 0.1.0)", file=sys.stderr)
            sys.exit(2)

        if args.dry_run:
            print(f"[dry-run] set pyproject.toml version -> {ver}")
        else:
            set_pyproject_version(ver)
            print(f"Set pyproject.toml version -> {ver}")
        version = ver
    else:
        version = get_version()
        print(f"pyproject.toml version: {version}")

    if args.dry_run:
        print(f"[dry-run] sync packaging/version_file.txt -> {version}")
        print(f"[dry-run] sync .release-please-manifest.json -> {version}")
        sys.exit(0)

    sync(version)
    sync_manifest(version)
