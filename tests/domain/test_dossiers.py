from hollow_lodge.domain.proofs import ProofDossier


def test_proof_dossier_tracks_framing_and_contributions_separately():
    dossier = ProofDossier.empty(
        dossier_id="dossier_crew_0001",
        crew_id="crew_0001",
        packet_lead_player_id="player_0001",
    )
    framed = dossier.with_framing(
        claim="The finger is not what the lot card says.",
        reasoning="The ledger contradicts the auction chain.",
        weaknesses="Material sample still missing.",
        provenance_concerns="Copied rubric needs official check.",
        evidence_ids=["fragment_starter_ledger.copy.player_0002.1"],
    )
    contributed = framed.with_contribution(
        player_id="player_0002",
        note="This may help us pressure the clerk.",
        evidence_ids=["fragment_starter_ledger.copy.player_0002.1"],
    )

    assert contributed.claim == "The finger is not what the lot card says."
    assert contributed.evidence_ids == ("fragment_starter_ledger.copy.player_0002.1",)
    assert contributed.member_contributions[0]["player_id"] == "player_0002"
    assert "contamination" not in str(contributed.member_contributions).lower()


def test_dossier_tracks_artifact_citations_separately_from_notes():
    dossier = ProofDossier.empty(
        dossier_id="dossier_crew_0001",
        crew_id="crew_0001",
        packet_lead_player_id="player_0001",
    ).with_artifact_citation(
        player_id="player_0001",
        artifact_id="artifact_ledger_rubric",
        claim="The ledger contradicts the public lot card.",
        quote="The last hand is redder and later than the binding.",
    )

    assert dossier.artifact_citations == (
        {
            "player_id": "player_0001",
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        },
    )
