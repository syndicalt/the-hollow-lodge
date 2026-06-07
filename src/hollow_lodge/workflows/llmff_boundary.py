from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from hollow_lodge.domain.actions import NormalizedAction


class HandlerNormalizationFrame(BaseModel):
    model_config = ConfigDict(frozen=True)

    origin: str
    type: str
    normalized: NormalizedAction


class HandlerNormalizer(Protocol):
    def __call__(
        self,
        intent: str,
        *,
        actor_player_id: str,
        crew_id: str,
    ) -> HandlerNormalizationFrame:
        """Translate player intent into a local normalized action draft."""
