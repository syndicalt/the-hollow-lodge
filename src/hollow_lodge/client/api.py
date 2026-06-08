from __future__ import annotations

import uuid
from typing import Any

import httpx


def new_command_key(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex}"


class HollowLodgeApi:
    def __init__(self, *, server_url: str, token: str | None = None):
        self.server_url = server_url.rstrip("/")
        self.token = token

    def register(
        self,
        *,
        invite_code: str,
        display_name: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            "/identity/register",
            json={"invite_code": invite_code, "display_name": display_name},
            idempotency_key=idempotency_key,
            authenticated=False,
        )

    def request_access_key(
        self,
        *,
        display_name: str,
        contact: str | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            "/identity/key-requests",
            json={"display_name": display_name, "contact": contact},
            idempotency_key=idempotency_key,
            authenticated=False,
        )

    def create_invite(self, *, admin_token: str, idempotency_key: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.server_url}/identity/admin/invites",
            headers={
                "Idempotency-Key": idempotency_key,
                "X-Hollow-Lodge-Admin-Token": admin_token,
            },
            json={},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def create_crew(self, *, name: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            "/crews",
            json={"name": name},
            idempotency_key=idempotency_key,
        )

    def join_crew(
        self,
        *,
        crew_id: str,
        join_code: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/crews/{crew_id}/join",
            json={"join_code": join_code},
            idempotency_key=idempotency_key,
        )

    def send_direct_message(
        self,
        *,
        recipient_player_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/chat/direct",
            json={
                "recipient_player_id": recipient_player_id,
                "body": body,
                "artifact_ids": list(artifact_ids or []),
            },
            idempotency_key=idempotency_key,
        )

    def send_crew_message(
        self,
        *,
        crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/chat/crew",
            json={
                "crew_id": crew_id,
                "body": body,
                "artifact_ids": list(artifact_ids or []),
            },
            idempotency_key=idempotency_key,
        )

    def send_crew_to_crew_message(
        self,
        *,
        sender_crew_id: str,
        recipient_crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/chat/crew-to-crew",
            json={
                "sender_crew_id": sender_crew_id,
                "recipient_crew_id": recipient_crew_id,
                "body": body,
                "artifact_ids": list(artifact_ids or []),
            },
            idempotency_key=idempotency_key,
        )

    def visible_events(self) -> list[dict[str, Any]]:
        return self.visible_events_since(since_sequence=0)

    def visible_events_since(self, *, since_sequence: int) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.server_url}/events",
            headers=self._auth_headers(),
            params={"since_sequence": since_sequence},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["events"]

    def contracts(self) -> dict[str, Any]:
        return self._get("/contracts")

    def inbox(self) -> dict[str, Any]:
        return self._get("/inbox")

    def me(self) -> dict[str, Any]:
        return self._get("/identity/me")

    def crew_board(self, *, crew_id: str) -> dict[str, Any]:
        return self._get(f"/crews/{crew_id}/board")

    def artifacts(self) -> dict[str, Any]:
        return self._get("/artifacts")

    def deals(self) -> dict[str, Any]:
        return self._get("/deals")

    def artifact(self, *, artifact_id: str) -> dict[str, Any]:
        return self._get(f"/artifacts/{artifact_id}")

    def inspect_artifact(self, *, artifact_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/artifacts/{artifact_id}/inspect",
            json={},
            idempotency_key=idempotency_key,
        )

    def transfer_artifact(
        self,
        *,
        artifact_id: str,
        recipient_player_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/artifacts/{artifact_id}/transfer",
            json={"recipient_player_id": recipient_player_id},
            idempotency_key=idempotency_key,
        )

    def propose_deal(
        self,
        *,
        contract_id: str,
        proposer_crew_id: str,
        recipient_crew_id: str,
        offered_artifact_ids: list[str] | tuple[str, ...],
        requested_artifact_ids: list[str] | tuple[str, ...],
        soft_terms: list[str] | tuple[str, ...],
        expires_phase: str | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            "/deals",
            json={
                "contract_id": contract_id,
                "proposer_crew_id": proposer_crew_id,
                "recipient_crew_id": recipient_crew_id,
                "offered_artifact_ids": list(offered_artifact_ids),
                "requested_artifact_ids": list(requested_artifact_ids),
                "soft_terms": list(soft_terms),
                "expires_phase": expires_phase,
            },
            idempotency_key=idempotency_key,
        )

    def accept_deal(self, *, deal_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/deals/{deal_id}/accept",
            json={},
            idempotency_key=idempotency_key,
        )

    def decline_deal(self, *, deal_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/deals/{deal_id}/decline",
            json={},
            idempotency_key=idempotency_key,
        )

    def cancel_deal(self, *, deal_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/deals/{deal_id}/cancel",
            json={},
            idempotency_key=idempotency_key,
        )

    def check_provenance(self, *, fragment_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/proofs/fragments/{fragment_id}/check/provenance",
            json={},
            idempotency_key=idempotency_key,
        )

    def submit_action(self, *, crew_id: str, intent: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            "/actions",
            json={"crew_id": crew_id, "intent": intent, "confirmed": True},
            idempotency_key=idempotency_key,
        )

    def dossier(self, *, crew_id: str) -> dict[str, Any]:
        return self._get(f"/proofs/dossiers/{crew_id}")

    def add_dossier_evidence(
        self,
        *,
        crew_id: str,
        fragment_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self.add_dossier_contribution(
            crew_id=crew_id,
            note="Added evidence fragment.",
            evidence_ids=[fragment_id],
            idempotency_key=idempotency_key,
        )

    def add_dossier_contribution(
        self,
        *,
        crew_id: str,
        note: str,
        evidence_ids: list[str] | tuple[str, ...],
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/proofs/dossiers/{crew_id}/contributions",
            json={"note": note, "evidence_ids": list(evidence_ids)},
            idempotency_key=idempotency_key,
        )

    def update_dossier_claim(
        self,
        *,
        crew_id: str,
        claim: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._patch(
            f"/proofs/dossiers/{crew_id}/framing",
            json={"claim": claim},
            idempotency_key=idempotency_key,
        )

    def cite_artifact_in_dossier(
        self,
        *,
        crew_id: str,
        artifact_id: str,
        claim: str,
        quote: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/proofs/dossiers/{crew_id}/artifact-citations",
            json={
                "artifact_id": artifact_id,
                "claim": claim,
                "quote": quote,
            },
            idempotency_key=idempotency_key,
        )

    def vote_packet_lead(
        self,
        *,
        crew_id: str,
        player_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/proofs/dossiers/{crew_id}/packet-lead/votes",
            json={"candidate_player_id": player_id},
            idempotency_key=idempotency_key,
        )

    def _post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        idempotency_key: str,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key}
        if authenticated:
            headers.update(self._auth_headers())
        response = httpx.post(
            f"{self.server_url}{path}",
            headers=headers,
            json=json,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _get(self, path: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.server_url}{path}",
            headers=self._auth_headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _patch(self, path: str, *, json: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        response = httpx.patch(
            f"{self.server_url}{path}",
            headers={**self._auth_headers(), "Idempotency-Key": idempotency_key},
            json=json,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            raise ValueError("authenticated API calls require a token")
        return {"Authorization": f"Bearer {self.token}"}
