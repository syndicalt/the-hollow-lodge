from __future__ import annotations

from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def test_default_data_dir_can_be_set_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path / "data"))

    app = create_app()

    assert app.state.event_store.path == tmp_path / "data" / "server-events.jsonl"


def test_default_app_keeps_artifact_and_deal_services_lazy(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path / "data"))

    app = create_app()

    assert not hasattr(app.state, "artifact_service")
    assert not hasattr(app.state, "deal_service")
    assert app.state.chat_service._artifact_service is None
    assert app.state.action_service._artifact_service is None


def test_health_response_stays_backward_compatible(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_diagnostics_reports_safe_operational_status(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "openai")
    monkeypatch.delenv("HOLLOW_LODGE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path))

    client = TestClient(create_app(invite_codes=["secret-invite"]))

    response = client.get("/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["server"]["version"] == "0.1.0"
    assert body["data"]["directory"] == str(tmp_path)
    assert body["data"]["event_log"]["path"] == str(tmp_path / "server-events.jsonl")
    assert body["data"]["event_log"]["exists"] is False
    assert body["data"]["event_log"]["status"] == "not_created"
    assert body["oracle"]["configured_provider"] == "openai"
    assert body["oracle"]["active_provider"] == "deterministic"
    assert body["oracle"]["ready"] is False
    assert body["oracle"]["fallback_active"] is True
    assert body["oracle"]["warnings"] == [
        "openai provider requested but HOLLOW_LODGE_OPENAI_API_KEY is not set; using deterministic fallback"
    ]
    assert "secret-invite" not in response.text


def test_diagnostics_reports_existing_event_log(tmp_path):
    event_log = tmp_path / "server-events.jsonl"
    event_log.write_text("", encoding="utf-8")
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/diagnostics")

    assert response.status_code == 200
    assert response.json()["data"]["event_log"] == {
        "path": str(event_log),
        "exists": True,
        "status": "available",
    }
