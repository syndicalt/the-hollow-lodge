from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NormalizedAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: str = Field(min_length=1)
    actor_player_id: str = Field(min_length=1)
    crew_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    approach: str = Field(min_length=1)
    risk_posture: str = Field(min_length=1)
    exposed_assets: list[str]
    crew_noise_impact: int = Field(ge=0)

    @classmethod
    def from_intent(
        cls,
        *,
        intent: str,
        actor_player_id: str,
        crew_id: str,
        action_number: int = 1,
    ) -> NormalizedAction:
        lower = intent.lower()
        exposed_assets: list[str] = []
        if "ledger" in lower:
            exposed_assets.append("fragment_starter_ledger")
        if any(marker in lower for marker in ("omen", "moth", "door", "occult")):
            exposed_assets.append("asset_door_omen")
        if "quiet" in lower or "inspect" in lower:
            scope = "proofwork"
            approach = "quiet inspection"
            risk_posture = "careful"
        else:
            scope = "pressure"
            approach = "direct pressure"
            risk_posture = "bold"
        return cls(
            intent=intent,
            actor_player_id=actor_player_id,
            crew_id=crew_id,
            scope=scope,
            approach=approach,
            risk_posture=risk_posture,
            exposed_assets=exposed_assets,
            crew_noise_impact=1 if action_number > 1 else 0,
        )
