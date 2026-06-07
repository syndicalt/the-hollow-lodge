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
