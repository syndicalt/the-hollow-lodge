from hollow_lodge.client.api import HollowLodgeApi


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
