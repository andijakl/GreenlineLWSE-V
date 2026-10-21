#!/usr/bin/env bash
# Update all development dependencies of Greenline LWSE-V to the latest versions
# that work with the current stable Home Assistant release, then validate.
# Usage: ./update-dependencies.sh [--check] [--skip-validation]

set -euo pipefail
shopt -s nullglob

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT
readonly PROJECT_PATH="$REPO_ROOT/pyproject.toml"
readonly HACS_PATH="$REPO_ROOT/hacs.json"
readonly TEST_PACKAGE="pytest-homeassistant-custom-component"
cd "$REPO_ROOT"

usage() {
    cat <<'EOF'
Usage: ./update-dependencies.sh [--check] [--skip-validation]

Update every development dependency to the latest version that works with the
current stable Home Assistant release, then run ./validate.sh:

  - pytest-homeassistant-custom-component: newest release that pins the
    current stable Home Assistant version (never a beta)
  - all other exact pins in pyproject.toml: newest stable release on PyPI
  - all transitive dependencies in uv.lock
  - pre-commit hook revisions
  - GitHub Actions used in .github/workflows

Options:
  --check            Only report available updates; leave all files unchanged.
  --skip-validation  Update dependencies without running ./validate.sh.
  -h, --help         Show this help.

Set NO_COLOR=1 to disable colored output.
EOF
}

check_only=false
skip_validation=false
while (($#)); do
    case "$1" in
        --check) check_only=true ;;
        --skip-validation) skip_validation=true ;;
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
    shift
done

# --- Output formatting -------------------------------------------------------

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    readonly BOLD=$'\e[1m' DIM=$'\e[2m' RED=$'\e[31m' GREEN=$'\e[32m'
    readonly YELLOW=$'\e[33m' BLUE=$'\e[34m' CYAN=$'\e[36m' RESET=$'\e[0m'
else
    readonly BOLD="" DIM="" RED="" GREEN="" YELLOW="" BLUE="" CYAN="" RESET=""
fi

section() {
    printf '\n%s%s▶ %s%s\n' "$BOLD" "$BLUE" "$1" "$RESET"
}
info() { printf '  %s•%s %s\n' "$CYAN" "$RESET" "$1"; }
ok() { printf '  %s✔%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '  %s⚠ %s%s\n' "$YELLOW" "$1" "$RESET"; }
fail() { printf '  %s✖ %s%s\n' "$RED" "$1" "$RESET" >&2; }

# Run a command quietly; show its output only if it fails.
run_quiet() {
    local description="$1"
    shift
    local log
    log="$(mktemp)"
    if "$@" >"$log" 2>&1; then
        ok "$description"
        rm -f "$log"
    else
        fail "$description failed:"
        sed "s/^/      ${DIM}/; s/\$/${RESET}/" "$log" >&2
        rm -f "$log"
        return 1
    fi
}

# Print "kind<TAB>name<TAB>old<TAB>new" rows from stdin as an aligned table.
print_changes() {
    local empty_message="$1" kind name old new count=0
    while IFS=$'\t' read -r kind name old new; do
        [[ -n "$kind" ]] || continue
        count=$((count + 1))
        case "$kind" in
            updated)
                printf '  %s↑%s %-44s %s%16s%s → %s%s%s\n' \
                    "$GREEN" "$RESET" "$name" "$DIM" "$old" "$RESET" "$BOLD$GREEN" "$new" "$RESET"
                ;;
            added)
                printf '  %s+%s %-44s %16s   %s%s%s\n' \
                    "$CYAN" "$RESET" "$name" "" "$CYAN" "$new" "$RESET"
                ;;
            removed)
                printf '  %s-%s %-44s %s%16s%s   %sremoved%s\n' \
                    "$RED" "$RESET" "$name" "$DIM" "$old" "$RESET" "$RED" "$RESET"
                ;;
            skipped)
                printf '  %s⚠%s %-44s %s%s%s\n' "$YELLOW" "$RESET" "$name" "$YELLOW" "$old" "$RESET"
                ;;
        esac
    done
    if ((count == 0)); then
        ok "$empty_message"
    fi
}

# --- Python helper -----------------------------------------------------------
# Network lookups and file parsing; prints tab-separated rows for the shell.

read -r -d '' PY_HELPER <<'PY' || true
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

PYPI = "https://pypi.org/pypi"
GITHUB = "https://api.github.com"
HEADERS = {"User-Agent": "greenline-lwse-v-update-dependencies"}
VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)(.*)$")


def fetch_json(url, headers=None):
    request = urllib.request.Request(url, headers={**HEADERS, **(headers or {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def release(version):
    """Return the numeric release tuple and the pre-release suffix."""
    match = VERSION_RE.match(version)
    if match is None:
        return None, version
    return tuple(int(part) for part in match.group(1).split(".")), match.group(2)


def is_final(version):
    numbers, suffix = release(version)
    return numbers is not None and not suffix


def ha_target():
    """Find the newest test package release for the current stable Home Assistant."""
    stable = fetch_json(f"{PYPI}/homeassistant/json")["info"]["version"]
    package = fetch_json(f"{PYPI}/pytest-homeassistant-custom-component/json")
    versions = sorted(
        (v for v in package["releases"] if is_final(v)),
        key=lambda v: release(v)[0],
        reverse=True,
    )
    chosen = None
    for version in versions[:100]:
        info = fetch_json(f"{PYPI}/pytest-homeassistant-custom-component/{version}/json")["info"]
        if info.get("yanked"):
            continue
        pin = next(
            (
                req.split("==", 1)[1].split(";")[0].strip()
                for req in info.get("requires_dist") or []
                if re.match(r"homeassistant\s*==", req)
            ),
            None,
        )
        if pin is None or not is_final(pin):
            continue
        if release(pin)[0] <= release(stable)[0]:
            chosen = (version, pin)
            break
    if chosen is None:
        sys.exit(f"No pytest-homeassistant-custom-component release supports Home Assistant {stable}")
    requires_python = fetch_json(f"{PYPI}/homeassistant/{chosen[1]}/json")["info"]["requires_python"]
    print("\t".join((chosen[0], chosen[1], stable, requires_python or "")))


def latest_pypi(name):
    print(fetch_json(f"{PYPI}/{name}/json")["info"]["version"])


def exact_pins(path):
    """Yield (group, name, version) for exact pins in pyproject.toml dependency groups."""
    groups = tomllib.loads(Path(path).read_text())["dependency-groups"]
    for group, requirements in groups.items():
        for requirement in requirements:
            if isinstance(requirement, str) and (
                match := re.fullmatch(r"\s*([A-Za-z0-9_.\-]+)\s*==\s*([^;\s]+)\s*", requirement)
            ):
                yield group, match.group(1), match.group(2)


def pins(path):
    for pin in exact_pins(path):
        print("\t".join(pin))


def lock_versions(path):
    return {
        package["name"]: package["version"]
        for package in tomllib.loads(Path(path).read_text())["package"]
        if "version" in package
    }


def hook_revisions(path):
    revisions, repo = {}, None
    for line in Path(path).read_text().splitlines():
        if match := re.match(r"\s*-\s*repo:\s*(\S+)", line):
            repo = match.group(1)
        elif (match := re.match(r"\s*rev:\s*['\"]?([^'\"\s#]+)", line)) and repo:
            revisions[repo.removeprefix("https://github.com/")] = match.group(1)
            repo = None
    return revisions


def pyproject_pins(path):
    return {f"{name} ({group})": version for group, name, version in exact_pins(path)}


def diff(kind, old_path, new_path):
    read = {"lock": lock_versions, "hooks": hook_revisions, "pins": pyproject_pins}[kind]
    old, new = read(old_path), read(new_path)
    for name in sorted(old.keys() | new.keys()):
        if name not in new:
            print(f"removed\t{name}\t{old[name]}\t")
        elif name not in old:
            print(f"added\t{name}\t\t{new[name]}")
        elif old[name] != new[name]:
            print(f"updated\t{name}\t{old[name]}\t{new[name]}")


def github_headers():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token and shutil.which("gh"):
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        token = result.stdout.strip() if result.returncode == 0 else None
    return {"Authorization": f"Bearer {token}"} if token else {}


def github_tag_exists(repo, tag, headers):
    try:
        fetch_json(f"{GITHUB}/repos/{repo}/git/ref/tags/{tag}", headers)
    except urllib.error.HTTPError:
        return False
    return True


def update_actions(*paths):
    """Move version-tagged actions to their latest stable release."""
    uses_re = re.compile(r"(uses:\s*)([\w.-]+/[\w.-]+)((?:/[^@\s]*)?)@(v\d+(?:\.\d+)*)(?=\s|$)")
    headers = github_headers()
    targets = {}
    texts = {path: Path(path).read_text() for path in paths}
    for text in texts.values():
        for match in uses_re.finditer(text):
            repo, ref = match.group(2), match.group(4)
            if (repo, ref) in targets:
                continue
            try:
                latest = fetch_json(f"{GITHUB}/repos/{repo}/releases/latest", headers)["tag_name"]
            except urllib.error.HTTPError as err:
                print(f"skipped\t{repo}\tGitHub API returned HTTP {err.code}\t")
                targets[(repo, ref)] = ref
                continue
            latest_numbers, suffix = release(latest)
            if latest_numbers is None or suffix:
                targets[(repo, ref)] = ref
                continue
            target = latest
            if ref.count(".") == 0:
                major = f"v{latest_numbers[0]}"
                if github_tag_exists(repo, major, headers):
                    target = major
            if release(target)[0] > release(ref)[0]:
                targets[(repo, ref)] = target
                print(f"updated\t{repo}\t{ref}\t{target}")
            else:
                targets[(repo, ref)] = ref

    def replace(match):
        target = targets.get((match.group(2), match.group(4)), match.group(4))
        return f"{match.group(1)}{match.group(2)}{match.group(3)}@{target}"

    for path, text in texts.items():
        updated = uses_re.sub(replace, text)
        if updated != text:
            Path(path).write_text(updated)


def main():
    command, *args = sys.argv[1:]
    {
        "ha-target": ha_target,
        "latest-pypi": latest_pypi,
        "pins": pins,
        "diff": diff,
        "update-actions": update_actions,
    }[command](*args)


main()
PY

py() {
    uv run --no-project --quiet python -c "$PY_HELPER" "$@"
}

# --- Preflight ---------------------------------------------------------------

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/." >&2
    exit 1
fi
if [[ ! -f "$PROJECT_PATH" || ! -f "$REPO_ROOT/uv.lock" ]]; then
    echo "Run this script from a Greenline LWSE-V repository checkout." >&2
    exit 1
fi

workflow_files=(.github/workflows/*.yml .github/workflows/*.yaml)
managed_files=(pyproject.toml uv.lock .pre-commit-config.yaml "${workflow_files[@]}")

printf '%s%sGreenline LWSE-V dependency update%s' "$BOLD" "$CYAN" "$RESET"
if [[ "$check_only" == true ]]; then
    printf ' %s(check only, no files are changed)%s' "$YELLOW" "$RESET"
fi
printf '\n'

if [[ "$check_only" == false ]] && command -v git >/dev/null 2>&1 \
    && [[ -n "$(git status --porcelain -- "${managed_files[@]}" 2>/dev/null)" ]]; then
    warn "Dependency files have uncommitted changes; they are included in the update."
fi

# Keep the original files to report changes and to roll back on errors.
backup_dir="$(mktemp -d)"
for file in "${managed_files[@]}"; do
    mkdir -p "$backup_dir/$(dirname -- "$file")"
    cp -- "$file" "$backup_dir/$file"
done

restore_on_exit=true
cleanup() {
    if [[ "$restore_on_exit" == true ]]; then
        for file in "${managed_files[@]}"; do
            cp -- "$backup_dir/$file" "$file"
        done
        if [[ "$check_only" == false ]]; then
            printf '\n'
            warn "Update aborted; restored the original dependency files."
        fi
    fi
    rm -rf -- "$backup_dir"
}
trap cleanup EXIT

# --- Home Assistant target ---------------------------------------------------

section "Home Assistant target"
target_info="$(py ha-target)"
IFS=$'\t' read -r test_package_version ha_version ha_stable ha_python <<<"$target_info"
info "Current stable Home Assistant: ${BOLD}${ha_stable}${RESET}"
if [[ "$ha_version" == "$ha_stable" ]]; then
    ok "$TEST_PACKAGE ${BOLD}${test_package_version}${RESET} tests against Home Assistant ${ha_version}"
else
    warn "No $TEST_PACKAGE release for ${ha_stable} yet; using ${test_package_version} (Home Assistant ${ha_version})"
fi

project_python="$(sed -n 's/^requires-python *= *"\(.*\)"/\1/p' "$PROJECT_PATH")"
if [[ -n "$ha_python" && "$ha_python" != "$project_python" ]]; then
    warn "Home Assistant ${ha_version} requires Python ${ha_python}, pyproject.toml declares ${project_python}"
    warn "Update requires-python, .python-version, mypy.ini and the pre-commit default_language_version together."
else
    ok "Python requirement matches Home Assistant (${project_python})"
fi
hacs_minimum="$(sed -n 's/.*"homeassistant": *"\([^"]*\)".*/\1/p' "$HACS_PATH")"
info "Minimum Home Assistant in hacs.json: ${hacs_minimum} ${DIM}(not changed automatically)${RESET}"

# --- Python dependencies -----------------------------------------------------

section "Python dependencies"
pinned="$(py pins "$PROJECT_PATH")"
while IFS=$'\t' read -r group name current; do
    if [[ "$name" == "$TEST_PACKAGE" ]]; then
        target="$test_package_version"
    else
        target="$(py latest-pypi "$name")"
    fi
    if [[ "$target" == "$current" ]]; then
        ok "${name} ${DIM}${current} (${group}) is up to date${RESET}"
    else
        run_quiet "${name} ${current} → ${target} (${group})" \
            uv add --group "$group" --bounds exact --no-sync "${name}==${target}"
    fi
done <<<"$pinned"
run_quiet "Upgraded all transitive dependencies in uv.lock" uv lock --upgrade

# --- Pre-commit hooks --------------------------------------------------------

section "Pre-commit hooks"
run_quiet "Updated pre-commit hook revisions" \
    uv run --locked --group quality pre-commit autoupdate

# --- GitHub Actions ----------------------------------------------------------

section "GitHub Actions"
if ((${#workflow_files[@]})); then
    action_changes="$(py update-actions "${workflow_files[@]}")"
    ok "Checked actions in ${#workflow_files[@]} workflow file(s)"
else
    action_changes=""
    info "No workflow files found"
fi

# --- Report ------------------------------------------------------------------

section "Direct dependencies"
py diff pins "$backup_dir/pyproject.toml" "$PROJECT_PATH" \
    | print_changes "All direct dependencies were already up to date"

section "Locked packages"
lock_changes="$(py diff lock "$backup_dir/uv.lock" uv.lock)"
print_changes "All locked packages were already up to date" <<<"$lock_changes"

section "Pre-commit hook revisions"
py diff hooks "$backup_dir/.pre-commit-config.yaml" .pre-commit-config.yaml \
    | print_changes "All hooks were already up to date"

section "GitHub Actions versions"
print_changes "All actions were already up to date" <<<"$action_changes"

changed_files=()
for file in "${managed_files[@]}"; do
    if ! cmp -s -- "$backup_dir/$file" "$file"; then
        changed_files+=("$file")
    fi
done

if [[ "$check_only" == true ]]; then
    section "Summary"
    if ((${#changed_files[@]})); then
        info "Updates are available for: ${changed_files[*]}"
        info "Run ${BOLD}./update-dependencies.sh${RESET} to apply them."
    else
        ok "Everything is up to date."
    fi
    exit 0
fi
restore_on_exit=false

section "Summary"
if ((${#changed_files[@]} == 0)); then
    ok "Everything was already up to date."
else
    ok "Updated: ${changed_files[*]}"
fi

if [[ "$skip_validation" == true ]]; then
    warn "Validation skipped; run ./validate.sh before committing."
    exit 0
fi

# --- Validation --------------------------------------------------------------

section "Validation"
if "$REPO_ROOT/validate.sh"; then
    printf '\n%s%s✔ Dependencies updated and validation passed (%ss).%s\n' \
        "$BOLD" "$GREEN" "$SECONDS" "$RESET"
else
    printf '\n%s%s✖ Validation failed after the dependency update.%s\n' "$BOLD" "$RED" "$RESET" >&2
    printf '  The updated files were kept so the failure can be fixed.\n' >&2
    printf '  Review with %sgit diff%s or revert with %sgit checkout -- %s%s\n' \
        "$BOLD" "$RESET" "$BOLD" "${changed_files[*]}" "$RESET" >&2
    exit 1
fi
