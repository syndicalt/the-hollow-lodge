from __future__ import annotations

from hollow_lodge.client.codex_mcp_config import (
    EXPECTED_CODEX_MCP_COMMAND,
    codex_mcp_server_command,
    codex_mcp_server_command_status,
    codex_mcp_server_registered,
    install_codex_mcp_server,
)


def test_install_codex_mcp_server_adds_config_section(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('model = "gpt-5.5"\n\n[mcp_servers.zaxy]\ncommand = "zaxy"\n', encoding="utf-8")

    changed = install_codex_mcp_server(config)

    assert changed is True
    assert config.read_text(encoding="utf-8") == (
        'model = "gpt-5.5"\n'
        "\n"
        "[mcp_servers.zaxy]\n"
        'command = "zaxy"\n'
        "\n"
        '[mcp_servers."the-hollow-lodge"]\n'
        'command = "hollow-lodge-mcp"\n'
    )


def test_install_codex_mcp_server_is_idempotent(tmp_path):
    config = tmp_path / "config.toml"

    assert install_codex_mcp_server(config) is True
    first = config.read_text(encoding="utf-8")
    assert install_codex_mcp_server(config) is False
    assert config.read_text(encoding="utf-8") == first


def test_codex_mcp_server_registered_reads_existing_config(tmp_path):
    config = tmp_path / "config.toml"

    assert codex_mcp_server_registered(config) is False
    assert codex_mcp_server_command(config) is None
    assert codex_mcp_server_command_status(config) == "missing"

    install_codex_mcp_server(config)

    assert codex_mcp_server_registered(config) is True
    assert codex_mcp_server_command(config) == EXPECTED_CODEX_MCP_COMMAND
    assert codex_mcp_server_command_status(config) == "ok"


def test_codex_mcp_server_command_status_detects_stale_command(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        '[mcp_servers."the-hollow-lodge"]\n'
        'command = "old-hollow-lodge-mcp --token secret-token"\n',
        encoding="utf-8",
    )

    assert codex_mcp_server_registered(config) is True
    assert codex_mcp_server_command(config) == "old-hollow-lodge-mcp --token secret-token"
    assert codex_mcp_server_command_status(config) == "mismatch"


def test_codex_mcp_server_command_status_handles_malformed_config(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[mcp_servers."the-hollow-lodge"\ncommand = "hollow-lodge-mcp"\n', encoding="utf-8")

    assert codex_mcp_server_registered(config) is False
    assert codex_mcp_server_command(config) is None
    assert codex_mcp_server_command_status(config) == "missing"


def test_codex_mcp_server_command_status_handles_unreadable_lodge_section(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[mcp_servers."the-hollow-lodge"]\nargs = ["serve"]\n', encoding="utf-8")

    assert codex_mcp_server_registered(config) is True
    assert codex_mcp_server_command(config) is None
    assert codex_mcp_server_command_status(config) == "unreadable"
