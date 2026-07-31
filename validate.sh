#!/usr/bin/env bash
# Run formatting, linting, type checks, and tests for Greenline LWSE-V.
# Usage: ./validate.sh

set -euo pipefail

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly MANIFEST_PATH="$REPO_ROOT/custom_components/greenline_lwse_v/manifest.json"
cd "$REPO_ROOT"

if [[ ! -f "$MANIFEST_PATH" ]]; then
    echo "Run this script from a checkout containing custom_components/greenline_lwse_v." >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/." >&2
    exit 1
fi

printf 'Running pre-commit checks...\n'
# Run pre-commit in the project environment so its Python hooks use the required Python version.
uv run --group test --with 'pre-commit==3.6.2' pre-commit run --all-files

printf '\nRunning the Home Assistant test suite with coverage...\n'
"$REPO_ROOT/run-tests.sh" coverage

printf '\nValidation completed successfully.\n'
