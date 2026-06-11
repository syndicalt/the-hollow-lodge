from __future__ import annotations

import sys

import httpx
import pytest

from hollow_lodge.client import cli
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.client.errors import (
    FriendlyApi,
    GameCommandError,
    translate_api_error,
)


def status_error(status_code: int, detail: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://lodge.invalid/actions")
    response = httpx.Response(status_code, json={"detail": detail}, request=request)
    return httpx.HTTPStatusError("rejected", request=request, response=response)


@pytest.mark.parametrize(
    ("detail", "fragment"),
    [
        ("phase locked", "already been locked"),
        ("phase still active", "cannot be locked yet"),
        ("not a crew member", "not a member of that crew"),
        ("packet lead only", "Packet Lead"),
    ],
)
def test_common_rejections_become_plain_language(detail, fragment):
    error = translate_api_error(status_error(409, detail))

    assert isinstance(error, GameCommandError)
    assert fragment in error.message
    assert error.detail == detail


def test_unknown_citation_artifact_names_the_artifact():
    error = translate_api_error(
        status_error(409, "unknown citation artifact: artifact_soot_sample")
    )

    assert "artifact_soot_sample" in error.message
    assert "not visible to your crew" in error.message


def test_unauthorized_points_at_onboarding():
    error = translate_api_error(status_error(401, "invalid token"))

    assert "credentials" in error.message


def test_unmapped_detail_passes_through_verbatim():
    error = translate_api_error(status_error(409, "rumor not found"))

    assert error.message == "rumor not found"


def test_connection_errors_name_the_server():
    request = httpx.Request("GET", "https://lodge.invalid/contracts")
    error = translate_api_error(httpx.ConnectError("boom", request=request))

    assert error is not None
    assert "lodge.invalid" in error.message


def test_friendly_api_translates_raised_status_errors():
    class StubApi:
        def submit_action(self, **kwargs):
            raise status_error(409, "phase locked")

        def contracts(self):
            return {"contracts": []}

    api = FriendlyApi(StubApi())

    assert api.contracts() == {"contracts": []}
    with pytest.raises(GameCommandError) as excinfo:
        api.submit_action(crew_id="crew_0001", intent="press the clerk")
    assert "already been locked" in excinfo.value.message


def test_error_message_is_usable_as_mcp_tool_error_text():
    error = translate_api_error(status_error(409, "phase locked"))

    assert "already been locked" in str(error)


def test_cli_entry_point_renders_friendly_error(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="https://lodge.invalid",
            token="token",
            player_id="player_0001",
        ),
    )

    class RejectingApi:
        def __init__(self, *, server_url: str, token: str | None = None):
            pass

        def contracts(self):
            raise status_error(403, "not a crew member")

    monkeypatch.setattr(cli, "HollowLodgeApi", RejectingApi)
    monkeypatch.setattr(
        sys, "argv", ["hollow-lodge", "contracts", "--config", str(config_path)]
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "not a member of that crew" in captured.err
    assert "Traceback" not in captured.err + captured.out
