from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
    )
    assert response.status_code == 201
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_crew_creation_and_join_are_authoritative_events(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    created = client.post(
        "/crews",
        headers=auth(ada["token"]),
        json={"name": "The Gilt Knives"},
    )
    assert created.status_code == 201
    crew_id = created.json()["crew_id"]

    joined = client.post(f"/crews/{crew_id}/join", headers=auth(grace["token"]))

    assert joined.status_code == 200
    assert joined.json()["member_count"] == 2
    events = (tmp_path / "server-events.jsonl").read_text()
    assert "crew.created" in events
    assert "crew.member.joined" in events


def test_wrong_crew_and_missing_actor_operations_are_denied(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    assert client.post("/crews", json={"name": "No Auth"}).status_code == 401
    assert client.post(
        "/crews/crew_missing/join",
        headers=auth(ada["token"]),
    ).status_code == 404


def test_crew_readiness_warns_below_three_but_allows_two_player_slice(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=auth(ada["token"]),
        json={"name": "The Gilt Knives"},
    ).json()

    joined = client.post(f"/crews/{crew['crew_id']}/join", headers=auth(grace["token"]))

    assert joined.status_code == 200
    assert joined.json()["ready_for_full_contracts"] is False
    assert "3-5" in joined.json()["readiness_warning"]
