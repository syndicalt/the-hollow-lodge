#!/usr/bin/env sh
set -eu

PACKAGE="${HOLLOW_LODGE_PACKAGE:-git+https://github.com/syndicalt/the-hollow-lodge.git}"

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' "uv is required to install The Hollow Lodge CLI."
  printf '%s\n' "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv tool install "$PACKAGE" --force

hollow-lodge codex install-mcp

if [ "${HOLLOW_LODGE_SKIP_ONBOARD:-0}" = "1" ]; then
  printf '%s\n' "Installed hollow-lodge. Run 'hollow-lodge onboard' when ready."
  printf '%s\n' "Run 'hollow-lodge doctor' to verify server, auth, MCP, and Codex render readiness."
  exit 0
fi

hollow-lodge onboard "$@"
printf '%s\n' "Run 'hollow-lodge doctor' to verify server, auth, MCP, and Codex render readiness."
