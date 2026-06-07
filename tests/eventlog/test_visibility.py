import pytest
from pydantic import ValidationError

from hollow_lodge.domain.events import EventVisibility, GameEvent, VisibilityPrincipal
from hollow_lodge.eventlog.visibility import Principal, filter_visible_events


def event(event_type: str, visibility: EventVisibility) -> GameEvent:
    return GameEvent.new(
        sequence=1,
        event_type=event_type,
        actor_id="server",
        visibility=visibility,
        payload={},
        previous_hash=None,
    )


def test_player_scoped_event_is_visible_only_to_named_player():
    visible = event("proof.fragment.received", EventVisibility.players(["player_ada"]))

    assert filter_visible_events([visible], Principal.player("player_ada")) == [visible]
    assert filter_visible_events([visible], Principal.player("player_grace")) == []


def test_server_only_event_never_appears_in_local_perspective_reads():
    hidden_truth = event("contract.hidden_truth.sealed", EventVisibility.server_only())

    assert filter_visible_events([hidden_truth], Principal.player("player_ada")) == []
    assert filter_visible_events([hidden_truth], Principal.crew("crew_ember")) == []
    assert filter_visible_events([hidden_truth], Principal.server()) == [hidden_truth]


def test_two_crew_visibility_fixture_is_explicitly_scoped_to_both_crews():
    rumor = event(
        "contract.rumor.leaked",
        EventVisibility.crews(["crew_ember", "crew_mirror"]),
    )

    assert filter_visible_events([rumor], Principal.crew("crew_ember")) == [rumor]
    assert filter_visible_events([rumor], Principal.crew("crew_mirror")) == [rumor]
    assert filter_visible_events([rumor], Principal.crew("crew_ash")) == []


def test_targeted_proof_visibility_fixture_names_sender_and_recipient_principals():
    proof = event(
        "proof.fragment.shared",
        EventVisibility.principals(
            players=["player_ada", "player_grace"],
            crews=["crew_ember", "crew_mirror"],
        ),
    )

    assert filter_visible_events([proof], Principal.player("player_ada")) == [proof]
    assert filter_visible_events([proof], Principal.player("player_grace")) == [proof]
    assert filter_visible_events([proof], Principal.crew("crew_ember")) == [proof]
    assert filter_visible_events([proof], Principal.crew("crew_mirror")) == [proof]
    assert filter_visible_events([proof], Principal.player("player_linus")) == []
    assert filter_visible_events([proof], Principal.crew("crew_ash")) == []


def test_targeted_chat_visibility_fixture_names_all_participants():
    chat = event(
        "chat.message.created",
        EventVisibility.principals(
            players=["player_ada", "player_grace"],
            crews=[],
        ),
    )

    assert filter_visible_events([chat], Principal.player("player_ada")) == [chat]
    assert filter_visible_events([chat], Principal.player("player_grace")) == [chat]
    assert filter_visible_events([chat], Principal.player("player_margaret")) == []


def test_empty_visibility_is_deny_by_default():
    secret = event("contract.hidden_truth.sealed", EventVisibility.deny_all())

    assert filter_visible_events([secret], Principal.player("player_ada")) == []
    assert filter_visible_events([secret], Principal.crew("crew_ember")) == []
    assert filter_visible_events([secret], Principal.server()) == []


def test_visibility_principals_require_valid_kind_and_id_shape():
    with pytest.raises(ValidationError):
        VisibilityPrincipal(kind="player")
    with pytest.raises(ValidationError):
        VisibilityPrincipal(kind="crew", id="")
    with pytest.raises(ValidationError):
        VisibilityPrincipal(kind="server", id="server_1")
    with pytest.raises(ValidationError):
        Principal(kind="ghost", id="player_ada")
