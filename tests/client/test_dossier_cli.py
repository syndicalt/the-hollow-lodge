from __future__ import annotations

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import ClientConfig, save_config


class FakeApi:
    def __init__(self, *, server_url: str, token: str | None = None):
        self.calls = []

    def dossier(self, *, crew_id: str):
        self.calls.append(("dossier", {"crew_id": crew_id}))
        return {"crew_id": crew_id, "claim": "The finger is a false relic."}

    def add_dossier_evidence(self, *, crew_id: str, fragment_id: str, idempotency_key: str):
        self.calls.append(
            (
                "add_dossier_evidence",
                {"crew_id": crew_id, "fragment_id": fragment_id, "idempotency_key": idempotency_key},
            )
        )
        return {"crew_id": crew_id, "evidence_ids": [fragment_id]}

    def update_dossier_claim(self, *, crew_id: str, claim: str, idempotency_key: str):
        self.calls.append(
            (
                "update_dossier_claim",
                {"crew_id": crew_id, "claim": claim, "idempotency_key": idempotency_key},
            )
        )
        return {"crew_id": crew_id, "claim": claim}

    def update_dossier_framing(
        self,
        *,
        crew_id: str,
        claim: str | None,
        evidence_ids: list[str] | None,
        reasoning: str | None,
        weaknesses: str | None,
        provenance_concerns: str | None,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "update_dossier_framing",
                {
                    "crew_id": crew_id,
                    "claim": claim,
                    "evidence_ids": evidence_ids,
                    "reasoning": reasoning,
                    "weaknesses": weaknesses,
                    "provenance_concerns": provenance_concerns,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"crew_id": crew_id, "claim": claim}

    def cite_artifact_in_dossier(
        self,
        *,
        crew_id: str,
        artifact_id: str,
        claim: str,
        quote: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "cite_artifact_in_dossier",
                {
                    "crew_id": crew_id,
                    "artifact_id": artifact_id,
                    "claim": claim,
                    "quote": quote,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"crew_id": crew_id, "artifact_id": artifact_id}

    def add_typed_dossier_claim(
        self,
        *,
        crew_id: str,
        subject_id: str,
        predicate: str,
        object_id: str | None,
        value: str | None,
        citation_artifact_ids: list[str],
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "add_typed_dossier_claim",
                {
                    "crew_id": crew_id,
                    "subject_id": subject_id,
                    "predicate": predicate,
                    "object_id": object_id,
                    "value": value,
                    "citation_artifact_ids": citation_artifact_ids,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"crew_id": crew_id, "subject_id": subject_id, "predicate": predicate}

    def vote_packet_lead(self, *, crew_id: str, player_id: str, idempotency_key: str):
        self.calls.append(
            (
                "vote_packet_lead",
                {"crew_id": crew_id, "player_id": player_id, "idempotency_key": idempotency_key},
            )
        )
        return {"crew_id": crew_id, "packet_lead_player_id": player_id}


def write_config(path):
    save_config(
        path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )


def test_dossier_commands_use_saved_config(tmp_path, monkeypatch):
    runner = CliRunner()
    clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    write_config(config_path)

    view = runner.invoke(cli.app, ["dossier", "--config", str(config_path)])
    evidence_preview = runner.invoke(
        cli.app,
        ["dossier", "add-evidence", "fragment_1", "--config", str(config_path)],
    )
    claim_preview = runner.invoke(
        cli.app,
        ["dossier", "claim", "The finger is false.", "--config", str(config_path)],
    )
    assert view.exit_code == 0
    assert evidence_preview.exit_code == 0
    assert "Preview: dossier_add_evidence" in evidence_preview.output
    assert "- crew_id: crew_0001" in evidence_preview.output
    assert "- fragment_id: fragment_1" in evidence_preview.output
    assert claim_preview.exit_code == 0
    assert "Preview: dossier_update_claim" in claim_preview.output
    assert "- crew_id: crew_0001" in claim_preview.output
    assert "- claim: The finger is false." in claim_preview.output
    assert len(clients) == 1
    assert clients[0].calls == [("dossier", {"crew_id": "crew_0001"})]

    evidence = runner.invoke(
        cli.app,
        ["dossier", "add-evidence", "fragment_1", "--confirm", "--config", str(config_path)],
    )
    claim = runner.invoke(
        cli.app,
        ["dossier", "claim", "The finger is false.", "--confirm", "--config", str(config_path)],
    )
    vote_preview = runner.invoke(
        cli.app,
        ["packet-lead", "vote", "player_0002", "--config", str(config_path)],
    )
    vote = runner.invoke(
        cli.app,
        ["packet-lead", "vote", "player_0002", "--confirm", "--config", str(config_path)],
    )

    assert evidence.exit_code == 0
    assert claim.exit_code == 0
    assert vote_preview.exit_code == 0
    assert "Preview: vote_packet_lead" in vote_preview.output
    assert "- crew_id: crew_0001" in vote_preview.output
    assert "- player_id: player_0002" in vote_preview.output
    assert vote.exit_code == 0
    assert clients[1].calls == [
        (
            "add_dossier_evidence",
            {
                "crew_id": "crew_0001",
                "fragment_id": "fragment_1",
                "idempotency_key": "dossier-evidence-key",
            },
        )
    ]
    assert clients[2].calls == [
        (
            "update_dossier_claim",
            {
                "crew_id": "crew_0001",
                "claim": "The finger is false.",
                "idempotency_key": "dossier-claim-key",
            },
        )
    ]
    assert clients[3].calls == [
        (
            "vote_packet_lead",
            {
                "crew_id": "crew_0001",
                "player_id": "player_0002",
                "idempotency_key": "packet-lead-vote-key",
            },
        )
    ]


def test_dossier_citation_and_frame_commands_send_only_requested_fields(tmp_path, monkeypatch):
    runner = CliRunner()
    clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    write_config(config_path)

    cite_preview = runner.invoke(
        cli.app,
        [
            "dossier",
            "cite-artifact",
            "artifact_ledger_rubric",
            "--claim",
            "The ledger contradicts the lot card.",
            "--quote",
            "The last hand is later.",
            "--config",
            str(config_path),
        ],
    )
    frame_preview = runner.invoke(
        cli.app,
        [
            "dossier",
            "frame",
            "--evidence-id",
            "fragment_1",
            "--weaknesses",
            "No direct witness.",
            "--config",
            str(config_path),
        ],
    )
    assert cite_preview.exit_code == 0
    assert "Preview: dossier_cite_artifact" in cite_preview.output
    assert "- crew_id: crew_0001" in cite_preview.output
    assert "- artifact_id: artifact_ledger_rubric" in cite_preview.output
    assert frame_preview.exit_code == 0
    assert "Preview: dossier_update_framing" in frame_preview.output
    assert "- crew_id: crew_0001" in frame_preview.output
    assert "- evidence_ids: ['fragment_1']" in frame_preview.output
    assert "- weaknesses: No direct witness." in frame_preview.output
    assert clients == []

    cite = runner.invoke(
        cli.app,
        [
            "dossier",
            "cite-artifact",
            "artifact_ledger_rubric",
            "--claim",
            "The ledger contradicts the lot card.",
            "--quote",
            "The last hand is later.",
            "--confirm",
            "--config",
            str(config_path),
        ],
    )
    frame = runner.invoke(
        cli.app,
        [
            "dossier",
            "frame",
            "--evidence-id",
            "fragment_1",
            "--weaknesses",
            "No direct witness.",
            "--confirm",
            "--config",
            str(config_path),
        ],
    )
    assert cite.exit_code == 0
    assert frame.exit_code == 0
    assert clients[0].calls == [
        (
            "cite_artifact_in_dossier",
            {
                "crew_id": "crew_0001",
                "artifact_id": "artifact_ledger_rubric",
                "claim": "The ledger contradicts the lot card.",
                "quote": "The last hand is later.",
                "idempotency_key": "dossier-cite-artifact-key",
            },
        )
    ]
    assert clients[1].calls == [
        (
            "update_dossier_framing",
            {
                "crew_id": "crew_0001",
                "claim": None,
                "evidence_ids": ["fragment_1"],
                "reasoning": None,
                "weaknesses": "No direct witness.",
                "provenance_concerns": None,
                "idempotency_key": "dossier-frame-key",
            },
        )
    ]


def test_dossier_typed_claim_command_previews_and_confirms(tmp_path, monkeypatch):
    runner = CliRunner()
    clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    write_config(config_path)

    preview = runner.invoke(
        cli.app,
        [
            "dossier",
            "typed-claim",
            "artifact_ledger_rubric",
            "contradicts_clean_provenance",
            "--object-id",
            "artifact_lot_card",
            "--citation",
            "artifact_ledger_rubric",
            "--citation",
            "artifact_lot_card",
            "--config",
            str(config_path),
        ],
    )

    assert preview.exit_code == 0
    assert "Preview: dossier_add_typed_claim" in preview.output
    assert "- crew_id: crew_0001" in preview.output
    assert "- subject_id: artifact_ledger_rubric" in preview.output
    assert "- predicate: contradicts_clean_provenance" in preview.output
    assert "- object_id: artifact_lot_card" in preview.output
    assert "- citation_artifact_ids: ['artifact_ledger_rubric', 'artifact_lot_card']" in (
        preview.output
    )
    assert clients == []

    confirmed = runner.invoke(
        cli.app,
        [
            "dossier",
            "typed-claim",
            "artifact_ledger_rubric",
            "contradicts_clean_provenance",
            "--object-id",
            "artifact_lot_card",
            "--citation",
            "artifact_ledger_rubric",
            "--crew-id",
            "crew_0002",
            "--confirm",
            "--config",
            str(config_path),
        ],
    )

    assert confirmed.exit_code == 0
    assert clients[0].calls == [
        (
            "add_typed_dossier_claim",
            {
                "crew_id": "crew_0002",
                "subject_id": "artifact_ledger_rubric",
                "predicate": "contradicts_clean_provenance",
                "object_id": "artifact_lot_card",
                "value": None,
                "citation_artifact_ids": ["artifact_ledger_rubric"],
                "idempotency_key": "dossier-typed-claim-key",
            },
        )
    ]


def test_dossier_typed_claim_requires_object_or_value(tmp_path):
    runner = CliRunner()
    config_path = tmp_path / "config.json"
    write_config(config_path)

    result = runner.invoke(
        cli.app,
        [
            "dossier",
            "typed-claim",
            "artifact_ledger_rubric",
            "contradicts_clean_provenance",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code != 0
    assert "typed claim requires --object-id or --value" in result.output
