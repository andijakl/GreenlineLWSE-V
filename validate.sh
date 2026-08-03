#!/usr/bin/env bash
# Update (optionally), format, lint, type-check, and test Greenline LWSE-V.
# Usage: ./validate.sh [--update]

set -euo pipefail

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly MANIFEST_PATH="$REPO_ROOT/custom_components/greenline_lwse_v/manifest.json"
readonly PROJECT_PATH="$REPO_ROOT/pyproject.toml"
cd "$REPO_ROOT"

usage() {
    cat <<'EOF'
Usage: ./validate.sh [--update]

Without options, validate the reproducible environment in uv.lock.
With --update, update exact direct dependency pins and pre-commit hooks first,
then run the same complete validation.
EOF
}

update_dependencies=false
case "${1:-}" in
    "") ;;
    --update) update_dependencies=true ;;
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

if [[ "$update_dependencies" == true ]]; then
    printf 'Updating uv-managed development dependencies...\n'
    uv add --group quality --bounds exact --upgrade pre-commit mypy
    uv add --group test --bounds exact --upgrade pytest-homeassistant-custom-component

    printf '\nUpdating pre-commit hook revisions...\n'
    uv run --locked --group quality pre-commit autoupdate
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
