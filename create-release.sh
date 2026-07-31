#!/usr/bin/env bash
# Build a HACS-compatible release archive for Greenline LWSE-V.
# Usage: ./create-release.sh [--skip-validation] [version]

set -euo pipefail

readonly DOMAIN="greenline_lwse_v"
readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly INTEGRATION_DIR="$REPO_ROOT/custom_components/$DOMAIN"
readonly MANIFEST_PATH="$INTEGRATION_DIR/manifest.json"
readonly RELEASES_DIR="$REPO_ROOT/releases"

usage() {
    cat <<'EOF'
Usage: ./create-release.sh [--skip-validation] [version]

Create releases/greenline_lwse_v-v<version>.zip with greenline_lwse_v/ at its root.
If supplied, version must match custom_components/greenline_lwse_v/manifest.json.
EOF
}

skip_validation=false
requested_version=""
while (($#)); do
    case "$1" in
        --skip-validation)
            skip_validation=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [[ -n "$requested_version" ]]; then
                echo "Only one version may be supplied." >&2
                usage >&2
                exit 2
            fi
            requested_version="$1"
            ;;
    esac
    shift
done

if [[ ! -f "$MANIFEST_PATH" ]]; then
    echo "manifest.json not found: $MANIFEST_PATH" >&2
    exit 1
fi

manifest_version="$(python3.14 -c 'import json, sys; from pathlib import Path; print(json.loads(Path(sys.argv[1]).read_text())["version"])' "$MANIFEST_PATH")"
version="${requested_version:-$manifest_version}"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid version '$version'; expected X.Y.Z." >&2
    exit 1
fi

if [[ "$version" != "$manifest_version" ]]; then
    echo "Requested version $version does not match manifest version $manifest_version." >&2
    echo "Update the manifest explicitly before creating a release." >&2
    exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
    echo "The 'zip' command is required to create a release archive." >&2
    exit 1
fi

if [[ "$skip_validation" == false ]]; then
    "$REPO_ROOT/validate.sh"
fi

mkdir -p "$RELEASES_DIR"
archive_path="$RELEASES_DIR/${DOMAIN}-v${version}.zip"
staging_root="$(mktemp -d "${TMPDIR:-/tmp}/${DOMAIN}-release.XXXXXX")"
trap 'rm -rf "$staging_root"' EXIT

mkdir -p "$staging_root/$DOMAIN"
cp -a "$INTEGRATION_DIR/." "$staging_root/$DOMAIN/"
rm -f "$archive_path"
(
    cd "$staging_root"
    zip -qr "$archive_path" "$DOMAIN"
)

printf 'Created %s\n' "$archive_path"
printf 'Archive contents:\n'
unzip -l "$archive_path"
