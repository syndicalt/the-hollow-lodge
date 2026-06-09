from __future__ import annotations

from pathlib import Path


CODEX_MCP_SECTION = '[mcp_servers."the-hollow-lodge"]'
CODEX_MCP_BLOCK = f'{CODEX_MCP_SECTION}\ncommand = "hollow-lodge-mcp"\n'


def install_codex_mcp_server(config_path: Path) -> bool:
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if CODEX_MCP_SECTION in existing:
        return False

    config_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    config_path.write_text(f"{prefix}{CODEX_MCP_BLOCK}", encoding="utf-8")
    return True


def codex_mcp_server_registered(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    return CODEX_MCP_SECTION in config_path.read_text(encoding="utf-8")
