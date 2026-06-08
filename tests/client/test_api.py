from hollow_lodge.client.api import HollowLodgeApi


def test_api_activates_contract_seed_with_admin_token(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {"contract_id": "contract_ash_window", "lifecycle_status": "active"}

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    api = HollowLodgeApi(server_url="http://testserver")
    seed = {"contract": {"contract_id": "contract_ash_window"}}

    result = api.activate_contract_seed(
        seed=seed,
        admin_token="admin-secret",
        idempotency_key="contract-activate-key",
    )

    assert result == {"contract_id": "contract_ash_window", "lifecycle_status": "active"}
    assert calls == [
        {
            "url": "http://testserver/contracts/admin/activate",
            "headers": {
                "Idempotency-Key": "contract-activate-key",
                "X-Hollow-Lodge-Admin-Token": "admin-secret",
            },
            "json": {"seed": seed},
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_archives_contract_with_admin_token(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {"contract_id": "contract_ash_window", "lifecycle_status": "archived"}

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    api = HollowLodgeApi(server_url="http://testserver")

    result = api.archive_contract(
        contract_id="contract_ash_window",
        admin_token="admin-secret",
        idempotency_key="contract-archive-key",
    )

    assert result == {"contract_id": "contract_ash_window", "lifecycle_status": "archived"}
    assert calls == [
        {
            "url": "http://testserver/contracts/admin/contract_ash_window/archive",
            "headers": {
                "Idempotency-Key": "contract-archive-key",
                "X-Hollow-Lodge-Admin-Token": "admin-secret",
            },
            "json": {},
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_gets_admin_player_detail_with_admin_token(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {
                "player_id": "player_0001",
                "display_name": "Ada",
                "token_revoked": False,
                "crew_ids": ["crew_0001"],
                "crew_count": 1,
            }

    def fake_get(url, *, headers, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.get", fake_get)
    api = HollowLodgeApi(server_url="http://testserver")

    result = api.get_player_detail(
        player_id="player_0001",
        admin_token="admin-secret",
    )

    assert result == {
        "player_id": "player_0001",
        "display_name": "Ada",
        "token_revoked": False,
        "crew_ids": ["crew_0001"],
        "crew_count": 1,
    }
    assert calls == [
        {
            "url": "http://testserver/identity/admin/players/player_0001",
            "headers": {"X-Hollow-Lodge-Admin-Token": "admin-secret"},
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_transfers_proof_fragment(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {"fragment_id": "fragment_starter_ledger.copy.player_0002.1"}

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    api = HollowLodgeApi(server_url="http://testserver", token="token")

    result = api.transfer_proof_fragment(
        fragment_id="fragment_starter_ledger",
        recipient_player_id="player_0002",
        idempotency_key="proof-transfer-key",
    )

    assert result == {"fragment_id": "fragment_starter_ledger.copy.player_0002.1"}
    assert calls == [
        {
            "url": "http://testserver/proofs/fragments/fragment_starter_ledger/transfer",
            "headers": {
                "Idempotency-Key": "proof-transfer-key",
                "Authorization": "Bearer token",
            },
            "json": {"recipient_player_id": "player_0002"},
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_cites_artifact_in_dossier(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {"dossier_id": "dossier_crew_0001"}

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    api = HollowLodgeApi(server_url="http://testserver", token="token")

    result = api.cite_artifact_in_dossier(
        crew_id="crew_0001",
        artifact_id="artifact_ledger_rubric",
        claim="The ledger contradicts the lot card.",
        quote="The last hand is later.",
        idempotency_key="dossier-cite-key",
    )

    assert result == {"dossier_id": "dossier_crew_0001"}
    assert calls == [
        {
            "url": "http://testserver/proofs/dossiers/crew_0001/artifact-citations",
            "headers": {
                "Idempotency-Key": "dossier-cite-key",
                "Authorization": "Bearer token",
            },
            "json": {
                "artifact_id": "artifact_ledger_rubric",
                "claim": "The ledger contradicts the lot card.",
                "quote": "The last hand is later.",
            },
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_updates_rich_dossier_framing(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {"crew_id": "crew_0001", "claim": "The relic is false."}

    def fake_patch(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.patch", fake_patch)
    api = HollowLodgeApi(server_url="http://testserver", token="token")

    result = api.update_dossier_framing(
        crew_id="crew_0001",
        claim="The relic is false.",
        evidence_ids=["fragment_1"],
        reasoning="The lot card and ledger disagree.",
        weaknesses=None,
        provenance_concerns="Copied hand.",
        idempotency_key="dossier-frame-key",
    )

    assert result == {"crew_id": "crew_0001", "claim": "The relic is false."}
    assert calls == [
        {
            "url": "http://testserver/proofs/dossiers/crew_0001/framing",
            "headers": {
                "Authorization": "Bearer token",
                "Idempotency-Key": "dossier-frame-key",
            },
            "json": {
                "claim": "The relic is false.",
                "evidence_ids": ["fragment_1"],
                "reasoning": "The lot card and ledger disagree.",
                "provenance_concerns": "Copied hand.",
            },
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_adds_dossier_contribution_with_note_and_evidence_ids(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {"dossier_id": "dossier_crew_0001"}

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    api = HollowLodgeApi(server_url="http://testserver", token="token")

    result = api.add_dossier_contribution(
        crew_id="crew_0001",
        note="The ledger hand changes after the chapel seal.",
        evidence_ids=["fragment_1", "artifact_ledger_rubric"],
        idempotency_key="dossier-contribute-key",
    )

    assert result == {"dossier_id": "dossier_crew_0001"}
    assert calls == [
        {
            "url": "http://testserver/proofs/dossiers/crew_0001/contributions",
            "headers": {
                "Idempotency-Key": "dossier-contribute-key",
                "Authorization": "Bearer token",
            },
            "json": {
                "note": "The ledger hand changes after the chapel seal.",
                "evidence_ids": ["fragment_1", "artifact_ledger_rubric"],
            },
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_edits_and_cancels_action(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return self.payload

    def fake_patch(url, *, headers, json, timeout):
        calls.append(
            {
                "method": "PATCH",
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response({"action_id": "action_000001", "intent": json["intent"]})

    def fake_delete(url, *, headers, timeout):
        calls.append(
            {
                "method": "DELETE",
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return Response({"action_id": "action_000001", "status": "canceled"})

    monkeypatch.setattr("httpx.patch", fake_patch)
    monkeypatch.setattr("httpx.delete", fake_delete)
    api = HollowLodgeApi(server_url="http://testserver", token="token")

    edited = api.edit_action(
        action_id="action_000001",
        intent="Inspect the ledger under candlelight.",
        idempotency_key="action-edit-key",
    )
    canceled = api.cancel_action(
        action_id="action_000001",
        idempotency_key="action-cancel-key",
    )

    assert edited == {
        "action_id": "action_000001",
        "intent": "Inspect the ledger under candlelight.",
    }
    assert canceled == {"action_id": "action_000001", "status": "canceled"}
    assert calls == [
        {
            "method": "PATCH",
            "url": "http://testserver/actions/action_000001",
            "headers": {
                "Authorization": "Bearer token",
                "Idempotency-Key": "action-edit-key",
            },
            "json": {"intent": "Inspect the ledger under candlelight."},
            "timeout": 10,
        },
        "raise_for_status",
        {
            "method": "DELETE",
            "url": "http://testserver/actions/action_000001",
            "headers": {
                "Authorization": "Bearer token",
                "Idempotency-Key": "action-cancel-key",
            },
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_submits_action_with_rumor_reference(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {
                "action_id": "action_000001",
                "responds_to_rumor_id": "rumor_msg_000001",
            }

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    api = HollowLodgeApi(server_url="http://testserver", token="token")

    result = api.submit_action(
        crew_id="crew_0001",
        intent="Verify the rumor quietly.",
        rumor_id="rumor_msg_000001",
        rumor_response_mode="contain",
        idempotency_key="action-submit-key",
    )

    assert result == {
        "action_id": "action_000001",
        "responds_to_rumor_id": "rumor_msg_000001",
    }
    assert calls == [
        {
            "url": "http://testserver/actions",
            "headers": {
                "Idempotency-Key": "action-submit-key",
                "Authorization": "Bearer token",
            },
            "json": {
                "crew_id": "crew_0001",
                "intent": "Verify the rumor quietly.",
                "confirmed": True,
                "rumor_id": "rumor_msg_000001",
                "rumor_response_mode": "contain",
            },
            "timeout": 10,
        },
        "raise_for_status",
    ]


def test_api_locks_auction_preview_phase(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {"status": "resolved", "standings": []}

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    api = HollowLodgeApi(server_url="http://testserver", token="token")

    result = api.lock_auction_preview_phase(
        contract_id="contract_false_finger",
        hours_elapsed=6,
        idempotency_key="phase-lock-key",
    )

    assert result == {"status": "resolved", "standings": []}
    assert calls == [
        {
            "url": "http://testserver/contracts/contract_false_finger/phases/auction-preview/lock",
            "headers": {
                "Idempotency-Key": "phase-lock-key",
                "Authorization": "Bearer token",
            },
            "json": {"hours_elapsed": 6},
            "timeout": 10,
        },
        "raise_for_status",
    ]
