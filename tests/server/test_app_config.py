from __future__ import annotations

from hollow_lodge.server.app import create_app


def test_default_data_dir_can_be_set_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path / "data"))

    app = create_app()

    assert app.state.event_store.path == tmp_path / "data" / "server-events.jsonl"


def test_default_app_has_artifact_and_deal_services(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path / "data"))

    app = create_app()

    assert app.state.artifact_service is app.state.chat_service._artifact_service
    assert app.state.artifact_service is app.state.action_service._artifact_service
    assert app.state.deal_service._artifact_service is app.state.artifact_service
