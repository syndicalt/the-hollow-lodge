from hollow_lodge.client.local_log import LocalEventLog


def test_local_only_handler_notes_are_not_authoritative_server_events(tmp_path):
    log = LocalEventLog(tmp_path / "local.jsonl")

    note = log.append_local_note(
        note_type="handler.summary",
        payload={"summary": "Ledger provenance is unclear."},
    )

    assert note["origin"] == "local"
    assert log.read() == [note]
    assert log.server_events_to_submit() == []


def test_visible_server_events_sync_to_local_perspective_log(tmp_path):
    log = LocalEventLog(tmp_path / "local.jsonl")
    visible_events = [
        {"event_id": "evt_1", "sequence": 1, "type": "chat.message.created", "payload": {"body": "A"}},
        {"event_id": "evt_2", "sequence": 2, "type": "crew.created", "payload": {"name": "Gilt"}},
    ]

    synced = log.sync_visible_server_events(visible_events)
    duplicate = log.sync_visible_server_events(visible_events)

    assert synced == 2
    assert duplicate == 0
    assert [event["origin"] for event in log.read()] == ["server", "server"]
    assert [event["event_id"] for event in log.read()] == ["evt_1", "evt_2"]
    assert log.server_events_to_submit() == []


def test_local_log_tracks_max_server_sequence_and_replays_visible_events(tmp_path):
    log = LocalEventLog(tmp_path / "local.jsonl")
    log.append_local_note(
        note_type="handler.summary",
        payload={"summary": "Keep the ledger quiet."},
    )
    log.sync_visible_server_events(
        [
            {
                "event_id": "evt_chat",
                "sequence": 3,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0001", "body": "Trade?"},
            },
            {
                "event_id": "evt_action",
                "sequence": 4,
                "type": "action.submitted",
                "payload": {"action": {"action_id": "action_000001", "intent": "Inspect."}},
            },
            {
                "event_id": "evt_transfer",
                "sequence": 5,
                "type": "proof.fragment.transferred",
                "payload": {
                    "surface": {
                        "fragment_id": "fragment_copy",
                        "content_summary": "Copied ledger fragment.",
                    }
                },
            },
            {
                "event_id": "evt_check",
                "sequence": 6,
                "type": "proof.provenance.checked",
                "payload": {
                    "result": {
                        "fragment_id": "fragment_copy",
                        "provenance_flags": ["copied-hand"],
                    }
                },
            },
            {
                "event_id": "evt_result",
                "sequence": 7,
                "type": "contract.phase.resolved",
                "payload": {
                    "reveal": {
                        "standings": [
                            {
                                "crew_id": "crew_0001",
                                "standing": "Strong lead",
                                "score": 82,
                            }
                        ]
                    }
                },
            },
        ]
    )

    rendered = log.render_replay(since_sequence=2)

    assert log.max_server_sequence() == 7
    assert rendered == [
        "3 player_0001: Trade?",
        "4 action action_000001: Inspect.",
        "5 proof fragment fragment_copy: Copied ledger fragment.",
        "6 provenance fragment_copy: copied-hand",
        "7 phase result: crew_0001 Strong lead 82",
    ]


def test_replay_sorts_recovered_older_visible_events_by_server_sequence(tmp_path):
    log = LocalEventLog(tmp_path / "local.jsonl")
    log.sync_visible_server_events(
        [
            {
                "event_id": "evt_newer",
                "sequence": 9,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0001", "body": "Join us."},
            }
        ]
    )
    log.sync_visible_server_events(
        [
            {
                "event_id": "evt_older",
                "sequence": 8,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0002", "body": "Ledger stayed."},
            },
            {
                "event_id": "evt_newer",
                "sequence": 9,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0001", "body": "Join us."},
            },
        ]
    )

    assert log.render_replay(since_sequence=0) == [
        "8 player_0002: Ledger stayed.",
        "9 player_0001: Join us.",
    ]
