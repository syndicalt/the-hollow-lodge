from fastapi.testclient import TestClient

from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.server.app import create_app
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.services import ActionService, CrewService


def register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def create_crew(client: TestClient, token: str) -> dict:
    response = client.post(
        "/crews",
        headers=command_auth(token, "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )
    assert response.status_code == 201
    return response.json()


def artifact_ids(response: dict) -> set[str]:
    return {artifact["artifact_id"] for artifact in response["artifacts"]}


def grant_events(client: TestClient, artifact_id: str) -> list:
    return [
        event
        for event in client.app.state.event_store.read()
        if event.type == "artifact.access.granted"
        and event.payload["artifact_id"] == artifact_id
    ]


def test_confirmed_action_awards_matching_artifact_to_crew(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"])

    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-chapel"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Question the chapel keeper about the debt mark.",
            "confirmed": True,
        },
    )
    visible = client.get("/artifacts", headers=auth(ada["token"]))

    assert submitted.status_code == 201
    assert visible.status_code == 200
    assert "artifact_chapel_debt_mark" in artifact_ids(visible.json())

    events = grant_events(client, "artifact_chapel_debt_mark")
    assert len(events) == 1
    assert events[0].visibility.model_dump(mode="json") == {
        "entries": [{"kind": "crew", "id": crew["crew_id"]}]
    }


def test_action_replay_repairs_missing_artifact_award_without_duplicate_grants(tmp_path):
    event_store = JsonlEventStore(tmp_path / "server-events.jsonl")
    crew_service = CrewService(event_store=event_store)
    crew = crew_service.create_crew(
        name="The Gilt Knives",
        owner_id="player_0001",
        idempotency_key="crew-create-gilt",
    )
    action_service = ActionService(
        event_store=event_store,
        crew_service=crew_service,
    )
    first = action_service.submit_action(
        player_id="player_0001",
        crew_id=crew.crew_id,
        intent="Question the chapel keeper about the debt mark.",
        confirmed=True,
        idempotency_key="action-submit-chapel",
    )
    assert grant_events_for_store(event_store, "artifact_chapel_debt_mark") == []

    artifact_service = ArtifactService(event_store=event_store)
    action_service.set_artifact_service(artifact_service)
    replay = action_service.submit_action(
        player_id="player_0001",
        crew_id=crew.crew_id,
        intent="Question the chapel keeper about the debt mark.",
        confirmed=True,
        idempotency_key="action-submit-chapel",
    )
    second_replay = action_service.submit_action(
        player_id="player_0001",
        crew_id=crew.crew_id,
        intent="Question the chapel keeper about the debt mark.",
        confirmed=True,
        idempotency_key="action-submit-chapel",
    )

    assert replay == first
    assert second_replay == first
    events = grant_events_for_store(event_store, "artifact_chapel_debt_mark")
    assert len(events) == 1
    assert events[0].payload["crew_ids"] == [crew.crew_id]


def grant_events_for_store(event_store: JsonlEventStore, artifact_id: str) -> list:
    return [
        event
        for event in event_store.read()
        if event.type == "artifact.access.granted"
        and event.payload["artifact_id"] == artifact_id
    ]
