from __future__ import annotations

from hollow_lodge.domain.scoring import AuctionPreviewScoreInput, score_auction_preview
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewResult,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
    validate_auction_preview_result,
)


class DeterministicResolutionOracle:
    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        scores = [
            score_auction_preview(
                AuctionPreviewScoreInput(
                    crew_id=crew.crew_id,
                    claim=crew.claim,
                    evidence_ids=crew.evidence_ids,
                    exposed_assets=crew.exposed_assets,
                    reasoning=crew.reasoning,
                    weaknesses=crew.weaknesses,
                    provenance_concerns=crew.provenance_concerns,
                    action_intents=crew.action_intents,
                    crew_noise=crew.crew_noise,
                )
            )
            for crew in packet.crews
        ]
        result = AuctionPreviewOracleResult(
            provider=OracleProviderMetadata(
                provider="deterministic",
                model=None,
                prompt_version="deterministic-v1",
            ),
            standings=tuple(
                AuctionPreviewCrewResult(
                    crew_id=score.crew_id,
                    score=score.total,
                    standing=score.standing,
                    strengths=score.strengths,
                    weaknesses=score.weaknesses,
                    penalties=score.penalties,
                    revealed_clues=score.revealed_clues,
                )
                for score in scores
            ),
            contract_state=(
                "Auction house provenance is now suspect.",
                "Rival alternate clue paths remain open.",
            ),
            narration="The auction preview resolves from submitted proof packets.",
            validation_warnings=(),
        )
        return validate_auction_preview_result(packet=packet, result=result)
