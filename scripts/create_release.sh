#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Create a GitHub Release
# =============================================================================

VERSION="$1"
NOTES="$2"
DIST_DIR="dist"

echo "Creating release $VERSION..."

# Find artifacts in dist/
artifacts=()
for f in "$DIST_DIR"/*; do
    if [ -f "$f" ]; then
        artifacts+=("$f")
    fi
done

if [ ${#artifacts[@]} -eq 0 ]; then
    echo "Error: No artifacts found in $DIST_DIR"
    exit 1
fi

# Create release
gh release create "$VERSION" \
    --title "Phantom Toolkit $VERSION" \
    --notes "$NOTES" \
    --draft \
    "${artifacts[@]}"

echo "Draft release created!"
