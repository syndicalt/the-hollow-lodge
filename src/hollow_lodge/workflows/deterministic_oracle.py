from __future__ import annotations

from hollow_lodge.domain.scoring import AuctionPreviewScoreInput, score_auction_preview
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewResult,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
    validate_auction_preview_result,
)


_PUBLIC_REVEAL_STRINGS_BY_SCORER_CLUE = {
    "auction-house provenance is now suspect": "Auction house provenance is now suspect.",
    "sealed-door omen remains viable": "Rival alternate clue paths remain open.",
}


def _safe_public_reveals(
    revealed_clues: tuple[str, ...],
    *,
    allowed_reveal_strings: tuple[str, ...],
) -> tuple[str, ...]:
    allowed_reveals = set(allowed_reveal_strings)
    return tuple(
        public_reveal
        for clue in revealed_clues
        if (public_reveal := _PUBLIC_REVEAL_STRINGS_BY_SCORER_CLUE.get(clue))
        is not None and public_reveal in allowed_reveals
    )


class DeterministicResolutionOracle:
    def runtime_metadata(self) -> OracleProviderMetadata:
        return OracleProviderMetadata(
            provider="deterministic",
            model=None,
            prompt_version="deterministic-v1",
        )

    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        scores = []
        for crew in packet.crews:
            score = score_auction_preview(
                AuctionPreviewScoreInput(
                    crew_id=crew.crew_id,
                    evidence_ids=crew.evidence_ids,
                    artifact_citations=tuple(
                        citation.model_dump(mode="json")
                        for citation in crew.artifact_citations
                    ),
                    known_edges=crew.known_edges,
                    exposed_assets=crew.exposed_assets,
                    compiled_actions=tuple(
                        action.model_dump(mode="json")
                        for action in crew.compiled_actions
                    ),
                    typed_claims=tuple(
                        claim.model_dump(mode="json")
                        for claim in crew.typed_claims
                    ),
                    crew_noise=crew.crew_noise,
                )
            )
            strengths = list(score.strengths)
            if crew.artifact_citations:
                strengths.append("cited artifact source material")
            if crew.known_edges:
                strengths.append("mapped evidence contradiction")
            adjusted_total = min(packet.score_max, score.total)
            adjusted_strengths = tuple(dict.fromkeys(strengths))
            scores.append(
                score.model_copy(
                    update={
                        "total": adjusted_total,
                        "standing": _standing(
                            total=adjusted_total,
                            strengths=adjusted_strengths,
                        ),
                        "strengths": adjusted_strengths,
                    }
                )
            )
        result = AuctionPreviewOracleResult(
            provider=self.runtime_metadata(),
            standings=tuple(
                AuctionPreviewCrewResult(
                    crew_id=score.crew_id,
                    score=score.total,
                    standing=score.standing,
                    strengths=score.strengths,
                    weaknesses=score.weaknesses,
                    penalties=score.penalties,
                    revealed_clues=_safe_public_reveals(
                        score.revealed_clues,
                        allowed_reveal_strings=packet.allowed_reveal_strings,
                    ),
                )
                for score in scores
            ),
            contract_state=tuple(packet.allowed_reveal_strings[:2]),
            narration="The auction preview resolves from submitted proof packets.",
            validation_warnings=(),
        )
        return validate_auction_preview_result(packet=packet, result=result)


def _standing(*, total: int, strengths: tuple[str, ...]) -> str:
    if total >= 70:
        return "Strong lead"
    if "occult clue may unlock alternate lane" in strengths:
        return "Viable but unstable"
    if total >= 40:
        return "Viable"
    return "Weak"
