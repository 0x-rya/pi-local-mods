#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_PACKAGE="@earendil-works/pi-coding-agent"
PI_PACKAGE_SPEC="${PI_PACKAGE}${PI_VERSION:+@$PI_VERSION}"

usage() {
  cat <<EOF
Usage: ./apply.sh [--bootstrap] [--upgrade-pi] [--no-bootstrap]

Options:
  --bootstrap   Install the global Pi package if it is missing (default behavior).
  --upgrade-pi  Install/update the global Pi package before applying patches.
                Set PI_VERSION=<version> to install a specific version.
  --no-bootstrap
                Do not install packages; only apply patches.
EOF
}

bootstrap=true
upgrade_pi=false
for arg in "$@"; do
  case "$arg" in
    --bootstrap)
      bootstrap=true
      ;;
    --upgrade-pi)
      bootstrap=true
      upgrade_pi=true
      ;;
    --no-bootstrap)
      bootstrap=false
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd python3
require_cmd node
if [[ -z "${PI_CODING_AGENT_DIR:-}" ]]; then
  require_cmd npm
fi

pi_package_dir() {
  if [[ -n "${PI_CODING_AGENT_DIR:-}" ]]; then
    printf '%s\n' "$PI_CODING_AGENT_DIR"
  else
    local npm_root
    npm_root="$(npm root -g)"
    printf '%s/%s\n' "$npm_root" "$PI_PACKAGE"
  fi
}

install_pi_if_needed() {
  if [[ -n "${PI_CODING_AGENT_DIR:-}" ]]; then
    if [[ ! -d "$PI_CODING_AGENT_DIR" ]]; then
      echo "PI_CODING_AGENT_DIR is set but does not exist: $PI_CODING_AGENT_DIR" >&2
      exit 1
    fi
    echo "Using PI_CODING_AGENT_DIR=$PI_CODING_AGENT_DIR; skipping global Pi install."
    return
  fi

  local package_dir
  package_dir="$(pi_package_dir)"
  if [[ "$upgrade_pi" == true ]]; then
    echo "Installing/updating $PI_PACKAGE_SPEC globally (network + global npm mutation)..."
    npm install -g "$PI_PACKAGE_SPEC"
  elif [[ ! -d "$package_dir" ]]; then
    echo "Global $PI_PACKAGE not found; installing $PI_PACKAGE_SPEC globally (network + global npm mutation)..."
    npm install -g "$PI_PACKAGE_SPEC"
  else
    echo "Found global $PI_PACKAGE at $package_dir"
  fi
}

if [[ "$bootstrap" == true ]]; then
  install_pi_if_needed
fi

python3 "$ROOT/scripts/apply.py"
