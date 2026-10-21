#!/usr/bin/env bash
# Format, lint, type-check, and test Greenline LWSE-V.
# Usage: ./validate.sh

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT
readonly MANIFEST_PATH="$REPO_ROOT/custom_components/greenline_lwse_v/manifest.json"
readonly PROJECT_PATH="$REPO_ROOT/pyproject.toml"
cd "$REPO_ROOT"

usage() {
    cat <<'EOF'
Usage: ./validate.sh

Validate the reproducible environment in uv.lock. To first update dependencies
to the latest versions for the current stable Home Assistant release, run
./update-dependencies.sh instead; it calls this script afterwards.
EOF
}

case "${1:-}" in
    "") ;;
    --help|-h)
        usage
        exit 0
        ;;
    *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 2
        ;;
esac
if (($# > 1)); then
    echo "Only one option may be supplied." >&2
    usage >&2
    exit 2
fi

if [[ ! -f "$MANIFEST_PATH" || ! -f "$PROJECT_PATH" ]]; then
    echo "Run this script from a Greenline LWSE-V repository checkout." >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/." >&2
    exit 1
fi

printf 'Checking the uv lockfile...\n'
uv lock --check

versions="$(
    uv run --locked python -c '
import json
import sys
import tomllib
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
project = tomllib.loads(Path(sys.argv[2]).read_text())
print("{}\t{}".format(manifest["version"], project["project"]["version"]))
' "$MANIFEST_PATH" "$PROJECT_PATH"
)"
IFS=$'\t' read -r manifest_version project_version <<<"$versions"
if [[ "$manifest_version" != "$project_version" ]]; then
    echo "Version mismatch: manifest=$manifest_version, pyproject=$project_version" >&2
    exit 1
fi
printf 'Version consistency check passed (%s).\n' "$manifest_version"

printf '\nRunning pre-commit checks...\n'
uv run --locked --group quality pre-commit run --all-files --show-diff-on-failure

printf '\nRunning the Home Assistant test suite with coverage...\n'
uv run --locked --group test pytest tests -v \
    --cov=custom_components.greenline_lwse_v \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-report=html

printf '\nValidation completed successfully.\n'
