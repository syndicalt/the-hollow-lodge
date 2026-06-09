#!/usr/bin/env sh
set -eu

PACKAGE="${HOLLOW_LODGE_PACKAGE:-git+https://github.com/syndicalt/the-hollow-lodge.git}"
SERVER_URL="${HOLLOW_LODGE_SERVER_URL:-}"

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' "uv is required to install The Hollow Lodge CLI."
  printf '%s\n' "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv tool install "$PACKAGE" --force

hollow-lodge codex install-mcp

run_doctor() {
  if [ "${HOLLOW_LODGE_SKIP_DOCTOR:-0}" = "1" ]; then
    printf '%s\n' "Skipping hollow-lodge doctor. Run it later to verify server, auth, MCP, and Codex render readiness."
    return
  fi
  if [ -n "$SERVER_URL" ]; then
    hollow-lodge doctor --server "$SERVER_URL"
    return
  fi
  hollow-lodge doctor
}

if [ "${HOLLOW_LODGE_SKIP_ONBOARD:-0}" = "1" ]; then
  printf '%s\n' "Installed hollow-lodge. Run 'hollow-lodge onboard' when ready."
  run_doctor
  exit 0
fi

if [ -n "$SERVER_URL" ]; then
  hollow-lodge onboard --server "$SERVER_URL" "$@"
else
  hollow-lodge onboard "$@"
fi
run_doctor
