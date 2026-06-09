from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ActionApproach = Literal[
    "provenance_research",
    "forgery_analysis",
    "infiltration",
    "deception",
    "social_leverage",
    "surveillance",
    "occult_analysis",
]
ActionScope = Literal["proofwork", "pressure", "rumor_response"]
RiskPosture = Literal["careful", "balanced", "bold"]


COMPILED_ACTION_VERSION = "compiled-action-v1"


class CompiledActionIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = COMPILED_ACTION_VERSION
    approach: ActionApproach
    scope: ActionScope
    risk_posture: RiskPosture
    target_ids: tuple[str, ...] = ()
    assets_staked: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()
    action_cost: int = Field(default=1, ge=1)
    crew_noise_impact: int = Field(default=0, ge=0)

    @property
    def compile_hash(self) -> str:
        encoded = self.model_dump_json().encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


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
    compiled_intent: CompiledActionIntent | None = None
    compile_hash: str | None = None

    @classmethod
    def from_intent(
        cls,
        *,
        intent: str,
        actor_player_id: str,
        crew_id: str,
        action_number: int = 1,
    ) -> NormalizedAction:
        compiled = compile_action_intent(
            intent=intent,
            action_number=action_number,
        )
        return cls(
            intent=intent,
            actor_player_id=actor_player_id,
            crew_id=crew_id,
            scope=compiled.scope,
            approach=compiled.approach,
            risk_posture=compiled.risk_posture,
            exposed_assets=list(compiled.assets_staked),
            crew_noise_impact=compiled.crew_noise_impact,
            compiled_intent=compiled,
            compile_hash=compiled.compile_hash,
        )


def compile_action_intent(
    *,
    intent: str,
    action_number: int = 1,
    allowed_target_ids: set[str] | None = None,
    allowed_asset_ids: set[str] | None = None,
    contract_terms: set[str] | None = None,
) -> CompiledActionIntent:
    lower = intent.casefold()
    targets: list[str] = []
    assets: list[str] = []
    matched_terms: list[str] = []

    if "ledger" in lower:
        _append_if_allowed(targets, "fragment_starter_ledger", allowed_target_ids)
        _append_if_allowed(assets, "fragment_starter_ledger", allowed_asset_ids)
        _append_if_allowed(targets, "artifact_ledger_rubric", allowed_target_ids)
        _append_if_allowed(assets, "artifact_ledger_rubric", allowed_asset_ids)
    if any(marker in lower for marker in ("omen", "moth", "door", "occult")):
        _append_if_allowed(targets, "asset_door_omen", allowed_target_ids)
        _append_if_allowed(assets, "asset_door_omen", allowed_asset_ids)

    for term in sorted(contract_terms or ()):
        normalized = term.casefold()
        if normalized and normalized in lower:
            matched_terms.append(term)

    if any(marker in lower for marker in ("forge", "forgery", "forged", "fake")):
        approach: ActionApproach = "forgery_analysis"
    elif any(marker in lower for marker in ("omen", "moth", "door", "occult", "resonance")):
        approach = "occult_analysis"
    elif any(marker in lower for marker in ("tail", "watch", "observe", "surveil")):
        approach = "surveillance"
    elif any(marker in lower for marker in ("lie", "false", "mislead", "deceive")):
        approach = "deception"
    elif any(marker in lower for marker in ("clerk", "pressure", "leverage", "bribe")):
        approach = "social_leverage"
    elif any(marker in lower for marker in ("infiltrate", "sneak", "break")):
        approach = "infiltration"
    else:
        approach = "provenance_research"

    if any(marker in lower for marker in ("rumor", "verify", "contain")):
        scope: ActionScope = "rumor_response"
    elif any(marker in lower for marker in ("pressure", "leverage", "bribe", "deceive")):
        scope = "pressure"
    else:
        scope = "proofwork"

    if any(marker in lower for marker in ("quiet", "careful", "cautious")):
        risk_posture: RiskPosture = "careful"
    elif any(marker in lower for marker in ("force", "bold", "break", "pressure")):
        risk_posture = "bold"
    else:
        risk_posture = "balanced"

    return CompiledActionIntent(
        approach=approach,
        scope=scope,
        risk_posture=risk_posture,
        target_ids=tuple(dict.fromkeys(targets)),
        assets_staked=tuple(dict.fromkeys(assets)),
        matched_terms=tuple(dict.fromkeys(matched_terms)),
        action_cost=1,
        crew_noise_impact=1 if action_number > 1 else 0,
    )


def _append_if_allowed(
    values: list[str],
    value: str,
    allowed_values: set[str] | None,
) -> None:
    if allowed_values is None or value in allowed_values:
        values.append(value)
