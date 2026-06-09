from __future__ import annotations

from pathlib import Path
import tomllib


CODEX_MCP_SECTION = '[mcp_servers."the-hollow-lodge"]'
EXPECTED_CODEX_MCP_COMMAND = "hollow-lodge-mcp"
CODEX_MCP_BLOCK = f'{CODEX_MCP_SECTION}\ncommand = "{EXPECTED_CODEX_MCP_COMMAND}"\n'


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


def codex_mcp_server_command(config_path: Path) -> str | None:
    if not config_path.exists():
        return None

    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None

    mcp_servers = parsed.get("mcp_servers")
    if not isinstance(mcp_servers, dict):
        return None

    lodge_server = mcp_servers.get("the-hollow-lodge")
    if not isinstance(lodge_server, dict):
        return None

    command = lodge_server.get("command")
    if not isinstance(command, str):
        return None

    return command


def codex_mcp_server_command_status(config_path: Path) -> str:
    if not codex_mcp_server_registered(config_path):
        return "missing"

    command = codex_mcp_server_command(config_path)
    if command is None:
        return "unreadable"
    if command != EXPECTED_CODEX_MCP_COMMAND:
        return "mismatch"
    return "ok"
