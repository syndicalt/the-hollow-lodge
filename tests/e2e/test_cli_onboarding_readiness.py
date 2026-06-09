import httpx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import load_config
from hollow_lodge.server.app import create_app


def _install_httpx_test_bridge(monkeypatch, client: TestClient) -> None:
    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.post(path, headers=headers, json=json)

    def fake_patch(url, headers=None, json=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.patch(path, headers=headers, json=json)

    def fake_delete(url, headers=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.delete(path, headers=headers)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "patch", fake_patch)
    monkeypatch.setattr(httpx, "delete", fake_delete)


def test_cli_onboards_installs_mcp_passes_doctor_and_renders_first_move(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()
    client = TestClient(create_app(data_dir=tmp_path / "server", invite_codes=["ada"]))
    _install_httpx_test_bridge(monkeypatch, client)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")

    config_path = tmp_path / "config.json"
    onboarding_path = tmp_path / "onboarding.json"
    codex_config = tmp_path / "codex.toml"
    local_log_path = tmp_path / "local.jsonl"

    onboard = runner.invoke(
        cli.app,
        [
            "onboard",
            "--server",
            "http://testserver",
            "--name",
            "Ada Corelumen",
            "--invite",
            "ada",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(onboarding_path),
        ],
    )

    assert onboard.exit_code == 0
    assert "registered player_0001" in onboard.output
    saved_config = load_config(config_path)
    assert saved_config.server_url == "http://testserver"
    assert saved_config.player_id == "player_0001"
    assert saved_config.display_name == "Ada Corelumen"
    assert saved_config.token
    assert onboarding_path.exists() is False

    mcp_install = runner.invoke(
        cli.app,
        [
            "codex",
            "install-mcp",
            "--config",
            str(codex_config),
            "--confirm",
        ],
    )

    assert mcp_install.exit_code == 0
    assert mcp_install.output == "registered the-hollow-lodge MCP server\n"
    assert 'command = "hollow-lodge-mcp"' in codex_config.read_text(encoding="utf-8")

    doctor = runner.invoke(
        cli.app,
        [
            "doctor",
            "--strict",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(onboarding_path),
            "--codex-config",
            str(codex_config),
            "--local-log",
            str(local_log_path),
        ],
    )

    assert doctor.exit_code == 0
    assert "server: ok http://testserver" in doctor.output
    assert "player: registered player_0001 display=Ada Corelumen active_crew=-" in (
        doctor.output
    )
    assert "auth: ok player_0001" in doctor.output
    assert "inbox: ok active_contracts=1" in doctor.output
    assert "event sync: ok synced=" in doctor.output
    assert "codex inbox render: ok surface=inbox" in doctor.output
    assert "codex what-now render: ok surface=what_now" in doctor.output
    assert f"mcp: registered {codex_config}" in doctor.output
    assert "mcp config command: ok hollow-lodge-mcp" in doctor.output
    assert "mcp command: available hollow-lodge-mcp" in doctor.output
    assert "strict: pass" in doctor.output

    what_now = runner.invoke(
        cli.app,
        [
            "what-now",
            "--config",
            str(config_path),
            "--local-log",
            str(local_log_path),
        ],
    )

    assert what_now.exit_code == 0
    assert "What Now: Ada Corelumen" in what_now.output
    assert "Player ID: player_0001" in what_now.output
    assert "The Saint's False Finger" in what_now.output

    serialized_outputs = "\n".join(
        (onboard.output, mcp_install.output, doctor.output, what_now.output)
    )
    for forbidden in (
        saved_config.token,
        "token_hash",
        "join_code",
        "idempotency_key",
        "Authorization",
        "payload",
        "origin",
        "server-events",
        "server-projections",
        str(tmp_path / "server"),
    ):
        assert forbidden not in serialized_outputs
