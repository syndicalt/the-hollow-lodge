from __future__ import annotations

from pathlib import Path

from hollow_lodge.client.codex_mcp_config import (
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

    install_codex_mcp_server(config)

    assert codex_mcp_server_registered(config) is True
