from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProofFragment(BaseModel):
    model_config = ConfigDict(frozen=True)

    fragment_id: str = Field(min_length=1)
    content_summary: str = Field(min_length=1)
    source_chain: tuple[str, ...]
    provenance_flags: tuple[str, ...] = ()
    provenance_checked: bool = False

    def copy_for_transfer(
        self,
        *,
        new_fragment_id: str,
        sender_player_id: str,
        recipient_player_id: str,
    ) -> ProofFragment:
        return self.model_copy(
            update={
                "fragment_id": new_fragment_id,
                "source_chain": (
                    *self.source_chain,
                    f"transfer:{sender_player_id}->{recipient_player_id}",
                ),
                "provenance_checked": False,
            }
        )

    def surface_view(self) -> dict:
        return {
            "fragment_id": self.fragment_id,
            "content_summary": self.content_summary,
            "source_chain": list(self.source_chain),
            "provenance_checked": self.provenance_checked,
        }

    def checked_view(self) -> dict:
        return {
            **self.surface_view(),
            "provenance_checked": True,
            "provenance_flags": list(self.provenance_flags),
        }
