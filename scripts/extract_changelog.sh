#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Extract changelog for a specific version
# =============================================================================

VERSION="$1"
CHANGELOG_FILE="CHANGELOG.md"

if [ ! -f "$CHANGELOG_FILE" ]; then
    echo "Error: $CHANGELOG_FILE not found."
    exit 1
fi

# Extract content between the version header and the next version header
# Assumes format: ## [Version] - Date
# or: ## Release [Version] (Date)

# Strip 'v' prefix if present to match cliff.toml format
CLEAN_VERSION="${VERSION#v}"

# We use awk to print lines between the start pattern and end pattern (exclusive)
awk -v ver="$CLEAN_VERSION" '
  BEGIN { printing = 0 }
  /^## .*Release/ || /^## \[[0-9]/ {
    if (index($0, ver)) {
      printing = 1
      next
    } else if (printing) {
      exit
    }
  }
  printing { print }
' "$CHANGELOG_FILE"
