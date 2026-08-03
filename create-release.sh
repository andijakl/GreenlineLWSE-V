#!/usr/bin/env bash
# Build a HACS-compatible release archive for NIBE Greenline LWSE-V.
# Usage: ./create-release.sh [--skip-validation] [version]

set -euo pipefail

readonly DOMAIN="greenline_lwse_v"
readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly INTEGRATION_DIR="$REPO_ROOT/custom_components/$DOMAIN"
readonly MANIFEST_PATH="$INTEGRATION_DIR/manifest.json"
readonly PROJECT_PATH="$REPO_ROOT/pyproject.toml"
readonly RELEASES_DIR="$REPO_ROOT/releases"

usage() {
    cat <<'EOF'
Usage: ./create-release.sh [--skip-validation] [version]

Create releases/greenline_lwse_v-v<version>.zip with greenline_lwse_v/ at its root.
If supplied, version must match both manifest.json and pyproject.toml.
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

if [[ ! -f "$MANIFEST_PATH" || ! -f "$PROJECT_PATH" ]]; then
    echo "Release metadata is missing from the repository checkout." >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/." >&2
    exit 1
fi

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
version="${requested_version:-$manifest_version}"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid version '$version'; expected X.Y.Z." >&2
    exit 1
fi

if [[ "$manifest_version" != "$project_version" ]]; then
    echo "Version mismatch: manifest=$manifest_version, pyproject=$project_version" >&2
    exit 1
fi

if [[ "$version" != "$manifest_version" ]]; then
    echo "Requested version $version does not match release metadata version $manifest_version." >&2
    echo "Update manifest.json and pyproject.toml explicitly before creating a release." >&2
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

# Refuse unexpected untracked files so local diagnostics, credentials, or
# experiments can never enter a release archive. The two bundled brand assets
# are explicitly allowed so a release can be smoke-tested before they are committed.
readonly BRAND_ICON_PATH="custom_components/$DOMAIN/brand/icon.png"
readonly BRAND_ICON_2X_PATH="custom_components/$DOMAIN/brand/icon@2x.png"
unexpected_untracked=false
while IFS= read -r -d '' source_path; do
    case "$source_path" in
        "$BRAND_ICON_PATH"|"$BRAND_ICON_2X_PATH") ;;
        *)
            echo "Refusing to package untracked integration file: $source_path" >&2
            unexpected_untracked=true
            ;;
    esac
done < <(
    git -C "$REPO_ROOT" ls-files -z --others --exclude-standard -- \
        "custom_components/$DOMAIN"
)
if [[ "$unexpected_untracked" == true ]]; then
    echo "Commit, ignore, or remove unexpected files before creating a release." >&2
    exit 1
fi

declare -A release_paths=()
while IFS= read -r -d '' source_path; do
    release_paths["$source_path"]=1
done < <(
    git -C "$REPO_ROOT" ls-files -z --cached -- "custom_components/$DOMAIN"
)
release_paths["$BRAND_ICON_PATH"]=1
release_paths["$BRAND_ICON_2X_PATH"]=1

for source_path in "${!release_paths[@]}"; do
    if [[ ! -f "$REPO_ROOT/$source_path" ]]; then
        echo "Required release file is missing: $source_path" >&2
        exit 1
    fi
    relative_path="${source_path#custom_components/}"
    destination="$staging_root/$relative_path"
    mkdir -p "$(dirname -- "$destination")"
    cp -- "$REPO_ROOT/$source_path" "$destination"
done

rm -f "$archive_path"
(
    cd "$staging_root"
    zip -qr "$archive_path" "$DOMAIN"
)

printf 'Created %s\n' "$archive_path"
printf 'Archive contents:\n'
unzip -l "$archive_path"
