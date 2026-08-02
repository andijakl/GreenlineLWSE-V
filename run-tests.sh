#!/usr/bin/env bash
# Run the standalone Home Assistant integration test suite with UV.
# Usage: ./run-tests.sh [all|coverage|<pytest arguments>]

set -euo pipefail

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/." >&2
    exit 1
fi

run_pytest() {
    uv run --locked --group test pytest "$@"
}

case "${1:-all}" in
    all)
        shift || true
        run_pytest tests -v "$@"
        ;;
    coverage)
        shift
        run_pytest tests -v \
            --cov=custom_components.greenline_lwse_v \
            --cov-report=term-missing \
            --cov-report=html \
            "$@"
        ;;
    help|--help|-h)
        cat <<'EOF'
Usage: ./run-tests.sh [all|coverage|<pytest arguments>]

  all        Run the complete test suite (default).
  coverage   Run all tests and write htmlcov/index.html.
  <args>     Pass arguments directly to pytest, for example:
             ./run-tests.sh tests/test_config_flow.py -k reauth
EOF
        ;;
    *)
        run_pytest "$@"
        ;;
esac
