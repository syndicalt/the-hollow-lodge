from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from datetime import UTC, datetime, timedelta

from hollow_lodge.domain.artifact_graph import ArtifactGraph
from hollow_lodge.domain.contracts import Contract, HiddenTruth
from hollow_lodge.domain.crews import Crew
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.domain.chat import ChatMessage
from hollow_lodge.domain.identity import (
    AccessKeyRequest,
    Invite,
    Player,
    generate_invite_code,
    generate_token,
    hash_token,
)
from hollow_lodge.domain.proofs import ProofDossier, ProofFragment
from hollow_lodge.domain.scoring import AuctionPreviewScoreInput
from hollow_lodge.domain.actions import NormalizedAction
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.visibility import Principal
from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH, STARTER_PUBLIC_ARTIFACT_IDS
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.artifact_unlocks import (
    action_unlock_candidates,
    auction_preview_phase_reward_artifact_id,
)
from hollow_lodge.server.projections import (
    contract_board_from_events,
    inbox_from_board,
    legacy_delta_for_standing,
    rumor_memory_from_events,
)
from hollow_lodge.server.contract_seed import ContractSeed, PhaseReward
from hollow_lodge.server.seed_data import STARTER_CAMPAIGN, STARTER_CONTRACT, STARTER_HIDDEN_TRUTH
from hollow_lodge.server.auth import authenticate_token
from hollow_lodge.server.rumors import visible_rumors_for_crew
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
    ResolutionOracle,
    validate_auction_preview_result,
)


JOIN_CODE_BYTES = 18
REGISTRATION_REPLAY_TTL = timedelta(minutes=15)
INVITE_REPLAY_TTL = timedelta(minutes=15)
SIDE_ACTION_LIMIT_PER_PHASE = 1
COMMAND_SERIALIZATION_LOCK = threading.RLock()
STARTER_FRAGMENT = ProofFragment(
    fragment_id="fragment_starter_ledger",
    content_summary="A red ledger rubric names three prior owners.",
    source_chain=("archive:lot-card",),
    provenance_flags=("copied-hand", "ink-after-binding"),
)


class IdentityService:
    def __init__(self, *, invite_codes: list[str], event_store: JsonlEventStore):
        self._unused_invites = set(invite_codes)
        self._used_invites: set[str] = set()
        self._invites: dict[str, Invite] = {}
        self._invite_replays: dict[str, str] = {}
        self._players: dict[str, Player] = {}
        self._key_requests: dict[str, AccessKeyRequest] = {}
        self._registration_replays: dict[str, tuple[Player, str]] = {}
        self._event_store = event_store
        self._registration_replay_path = event_store.path.with_suffix(".registration-replays.json")
        self._invite_replay_path = event_store.path.with_suffix(".invite-replays.json")
        self._lock = threading.RLock()
        self._rebuild_from_events()

    def register(
        self,
        *,
        invite_code: str,
        display_name: str,
        idempotency_key: str,
    ) -> tuple[Player, str]:
        with self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if idempotency_key in self._registration_replays:
                self._ensure_registration_replay_matches(
                    existing,
                    invite_code=invite_code,
                    display_name=display_name,
                )
                return self._registration_replays[idempotency_key]
            if existing is not None:
                self._ensure_registration_replay_matches(
                    existing,
                    invite_code=invite_code,
                    display_name=display_name,
                )
                if idempotency_key in self._registration_replays:
                    return self._registration_replays[idempotency_key]
                raise ValueError("registration replay token unavailable")
            if invite_code in self._used_invites:
                raise ValueError("invite already used")
            invite_hash = hash_token(invite_code)
            invite = self._invite_by_code(invite_code)
            if invite_code not in self._unused_invites and invite is None:
                raise ValueError("invalid invite")
            player_id = f"player_{len(self._players) + 1:04d}"
            token = generate_token()
            player = Player(
                player_id=player_id,
                display_name=display_name,
                token_hash=hash_token(token),
            )
            self._unused_invites.discard(invite_code)
            self._used_invites.add(invite_code)
            if invite is not None:
                self._invites[invite.invite_id] = Invite(
                    invite_id=invite.invite_id,
                    invite_hash=invite.invite_hash,
                    used=True,
                )
            self._players[player_id] = player
            self._event_store.append_command(
                event_type="identity.player.registered",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "player_id": player_id,
                    "display_name": display_name,
                    "invite_hash": invite_hash,
                    "token_hash": player.token_hash,
                },
                idempotency_key=idempotency_key,
            )
            self._remember_registration_replay(idempotency_key, player, token)
            return player, token

    def create_invite(self, *, idempotency_key: str) -> str:
        with self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if idempotency_key in self._invite_replays:
                self._ensure_invite_replay_matches(existing)
                return self._invite_replays[idempotency_key]
            if existing is not None:
                self._ensure_invite_replay_matches(existing)
                if idempotency_key in self._invite_replays:
                    return self._invite_replays[idempotency_key]
                raise ValueError("invite replay code unavailable")
            invite_id = f"invite_{len(self._invites) + 1:04d}"
            invite_code = generate_invite_code()
            invite_hash = hash_token(invite_code)
            self._invites[invite_id] = Invite(invite_id=invite_id, invite_hash=invite_hash)
            self._event_store.append_command(
                event_type="identity.invite.created",
                actor_id="admin",
                visibility=EventVisibility.server_only(),
                payload={
                    "invite_id": invite_id,
                    "invite_hash": invite_hash,
                    "used": False,
                },
                idempotency_key=idempotency_key,
            )
            self._remember_invite_replay(idempotency_key, invite_code)
            return invite_code

    def list_access_key_requests(self) -> list[AccessKeyRequest]:
        with self._lock:
            return sorted(
                self._key_requests.values(),
                key=lambda request: request.request_id,
            )

    def list_invites(self) -> list[Invite]:
        with self._lock:
            return sorted(
                self._invites.values(),
                key=lambda invite: invite.invite_id,
            )

    def list_players(self) -> list[Player]:
        with self._lock:
            return sorted(
                self._players.values(),
                key=lambda player: player.player_id,
            )

    def player_by_id(self, player_id: str) -> Player:
        with self._lock:
            return self._players[player_id]

    def approve_access_key_request(
        self,
        *,
        request_id: str,
        idempotency_key: str,
    ) -> tuple[AccessKeyRequest, str]:
        with self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if idempotency_key in self._invite_replays:
                self._ensure_key_request_approval_replay_matches(
                    existing,
                    request_id=request_id,
                )
                return self._key_requests[request_id], self._invite_replays[idempotency_key]
            if existing is not None:
                self._ensure_key_request_approval_replay_matches(
                    existing,
                    request_id=request_id,
                )
                if idempotency_key in self._invite_replays:
                    return self._key_requests[request_id], self._invite_replays[idempotency_key]
                raise ValueError("invite replay code unavailable")
            key_request = self._key_requests.get(request_id)
            if key_request is None:
                raise KeyError(request_id)
            if key_request.status != "pending":
                raise ValueError("key request already approved")
            invite_id = f"invite_{len(self._invites) + 1:04d}"
            invite_code = generate_invite_code()
            invite_hash = hash_token(invite_code)
            approved = AccessKeyRequest(
                request_id=key_request.request_id,
                display_name=key_request.display_name,
                contact=key_request.contact,
                status="approved",
            )
            self._key_requests[request_id] = approved
            self._invites[invite_id] = Invite(invite_id=invite_id, invite_hash=invite_hash)
            self._event_store.append_command(
                event_type="identity.key_request.approved",
                actor_id="admin",
                visibility=EventVisibility.server_only(),
                payload={
                    "request_id": request_id,
                    "status": approved.status,
                    "invite_id": invite_id,
                    "invite_hash": invite_hash,
                    "used": False,
                },
                idempotency_key=idempotency_key,
            )
            self._remember_invite_replay(idempotency_key, invite_code)
            return approved, invite_code

    def request_access_key(
        self,
        *,
        display_name: str,
        contact: str | None,
        idempotency_key: str,
    ) -> AccessKeyRequest:
        with self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                self._ensure_key_request_replay_matches(
                    existing,
                    display_name=display_name,
                    contact=contact,
                )
                return self._key_requests[existing.payload["request_id"]]
            request_id = f"key_request_{len(self._key_requests) + 1:04d}"
            key_request = AccessKeyRequest(
                request_id=request_id,
                display_name=display_name,
                contact=contact,
            )
            self._key_requests[request_id] = key_request
            self._event_store.append_command(
                event_type="identity.key_request.created",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "request_id": request_id,
                    "display_name": display_name,
                    "contact": contact,
                    "status": key_request.status,
                },
                idempotency_key=idempotency_key,
            )
            return key_request

    def authenticate(self, token: str) -> Player | None:
        with self._lock:
            return authenticate_token(self._players, token)

    def revoke_player_token(self, player_id: str) -> None:
        with self._lock:
            player = self._players[player_id]
            self._players[player_id] = Player(
                player_id=player.player_id,
                display_name=player.display_name,
                token_hash=player.token_hash,
                token_revoked=True,
            )
            self._event_store.append_command(
                event_type="identity.token.revoked",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={"player_id": player_id},
                idempotency_key=f"identity.revoke.{player_id}",
            )

    def has_player(self, player_id: str) -> bool:
        with self._lock:
            return player_id in self._players

    def _rebuild_from_events(self) -> None:
        replay_tokens = self._load_registration_replay_tokens(now=datetime.now(UTC))
        replay_invites = self._load_invite_replay_codes(now=datetime.now(UTC))
        for event in self._event_store.read():
            if event.type == "identity.player.registered":
                invite_hash = event.payload.get("invite_hash")
                invite_code = event.payload.get("invite_code")
                if invite_code is not None:
                    invite_hash = hash_token(invite_code)
                if invite_hash is not None:
                    for seeded_invite in list(self._unused_invites):
                        if secrets.compare_digest(hash_token(seeded_invite), invite_hash):
                            self._unused_invites.discard(seeded_invite)
                            self._used_invites.add(seeded_invite)
                            break
                self._players[event.payload["player_id"]] = Player(
                    player_id=event.payload["player_id"],
                    display_name=event.payload["display_name"],
                    token_hash=event.payload["token_hash"],
                )
                if event.idempotency_key is not None:
                    token = replay_tokens.get(event.idempotency_key)
                    if token is not None:
                        self._registration_replays[event.idempotency_key] = (
                            self._players[event.payload["player_id"]],
                            token,
                        )
                if invite_hash is not None:
                    for invite_id, invite in list(self._invites.items()):
                        if secrets.compare_digest(invite.invite_hash, invite_hash):
                            self._invites[invite_id] = Invite(
                                invite_id=invite.invite_id,
                                invite_hash=invite.invite_hash,
                                used=True,
                            )
                            break
            elif event.type == "identity.invite.created":
                self._invites[event.payload["invite_id"]] = Invite(
                    invite_id=event.payload["invite_id"],
                    invite_hash=event.payload["invite_hash"],
                    used=event.payload["used"],
                )
                if event.idempotency_key is not None:
                    invite_code = replay_invites.get(event.idempotency_key)
                    if invite_code is not None:
                        self._invite_replays[event.idempotency_key] = invite_code
            elif event.type == "identity.token.revoked":
                player = self._players[event.payload["player_id"]]
                self._players[player.player_id] = Player(
                    player_id=player.player_id,
                    display_name=player.display_name,
                    token_hash=player.token_hash,
                    token_revoked=True,
                )
            elif event.type == "identity.key_request.created":
                self._key_requests[event.payload["request_id"]] = AccessKeyRequest(
                    request_id=event.payload["request_id"],
                    display_name=event.payload["display_name"],
                    contact=event.payload.get("contact"),
                    status=event.payload["status"],
                )
            elif event.type == "identity.key_request.approved":
                key_request = self._key_requests[event.payload["request_id"]]
                self._key_requests[key_request.request_id] = AccessKeyRequest(
                    request_id=key_request.request_id,
                    display_name=key_request.display_name,
                    contact=key_request.contact,
                    status=event.payload["status"],
                )
                self._invites[event.payload["invite_id"]] = Invite(
                    invite_id=event.payload["invite_id"],
                    invite_hash=event.payload["invite_hash"],
                    used=event.payload["used"],
                )
                if event.idempotency_key is not None:
                    invite_code = replay_invites.get(event.idempotency_key)
                    if invite_code is not None:
                        self._invite_replays[event.idempotency_key] = invite_code

    def _event_by_idempotency_key(self, idempotency_key: str):
        for event in self._event_store.read():
            if event.idempotency_key == idempotency_key:
                return event
        return None

    def _ensure_registration_replay_matches(
        self,
        event,
        *,
        invite_code: str,
        display_name: str,
    ) -> None:
        if event is None or event.type != "identity.player.registered":
            raise ValueError("idempotency key conflict")
        event_invite_hash = event.payload.get("invite_hash")
        if event_invite_hash is None and "invite_code" in event.payload:
            event_invite_hash = hash_token(event.payload["invite_code"])
        if (
            event_invite_hash != hash_token(invite_code)
            or event.payload["display_name"] != display_name
        ):
            raise ValueError("idempotency key conflict")

    def _ensure_key_request_replay_matches(
        self,
        event,
        *,
        display_name: str,
        contact: str | None,
    ) -> None:
        if event is None or event.type != "identity.key_request.created":
            raise ValueError("idempotency key conflict")
        if event.payload["display_name"] != display_name or event.payload.get("contact") != contact:
            raise ValueError("idempotency key conflict")

    def _ensure_invite_replay_matches(self, event) -> None:
        if event is None or event.type != "identity.invite.created":
            raise ValueError("idempotency key conflict")

    def _ensure_key_request_approval_replay_matches(
        self,
        event,
        *,
        request_id: str,
    ) -> None:
        if event is None or event.type != "identity.key_request.approved":
            raise ValueError("idempotency key conflict")
        if event.payload["request_id"] != request_id:
            raise ValueError("idempotency key conflict")

    def _invite_by_code(self, invite_code: str) -> Invite | None:
        invite_hash = hash_token(invite_code)
        for invite in self._invites.values():
            if not invite.used and secrets.compare_digest(invite.invite_hash, invite_hash):
                return invite
        return None

    def _remember_registration_replay(
        self,
        idempotency_key: str,
        player: Player,
        token: str,
    ) -> None:
        self._registration_replays[idempotency_key] = (player, token)
        now = datetime.now(UTC)
        replay_tokens = self._load_registration_replay_tokens(now=now)
        replay_tokens[idempotency_key] = {
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "token": token,
        }
        self._registration_replay_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self._registration_replay_path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(replay_tokens, handle, sort_keys=True)
            handle.write("\n")
        os.chmod(self._registration_replay_path, 0o600)

    def _load_registration_replay_tokens(self, *, now: datetime) -> dict[str, str]:
        if not self._registration_replay_path.exists():
            return {}
        with self._registration_replay_path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        valid: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            created_at = datetime.fromisoformat(str(value["created_at"]).replace("Z", "+00:00"))
            if now - created_at <= REGISTRATION_REPLAY_TTL:
                valid[str(key)] = str(value["token"])
        return valid

    def _remember_invite_replay(self, idempotency_key: str, invite_code: str) -> None:
        self._invite_replays[idempotency_key] = invite_code
        now = datetime.now(UTC)
        replay_invites = self._load_invite_replay_codes(now=now)
        replay_invites[idempotency_key] = {
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "invite_code": invite_code,
        }
        self._invite_replay_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self._invite_replay_path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(replay_invites, handle, sort_keys=True)
            handle.write("\n")
        os.chmod(self._invite_replay_path, 0o600)

    def _load_invite_replay_codes(self, *, now: datetime) -> dict[str, str]:
        if not self._invite_replay_path.exists():
            return {}
        with self._invite_replay_path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        valid: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            created_at = datetime.fromisoformat(str(value["created_at"]).replace("Z", "+00:00"))
            if now - created_at <= INVITE_REPLAY_TTL:
                valid[str(key)] = str(value["invite_code"])
        return valid


class CrewService:
    def __init__(self, *, event_store: JsonlEventStore):
        self._crews: dict[str, Crew] = {}
        self._event_store = event_store
        self._lock = threading.RLock()
        self._rebuild_from_events()

    def create_crew(self, *, name: str, owner_id: str, idempotency_key: str) -> Crew:
        with self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                self._ensure_crew_create_replay_matches(
                    existing,
                    owner_id=owner_id,
                    name=name,
                )
                return self._crews[existing.payload["crew_id"]]
            crew_id = f"crew_{len(self._crews) + 1:04d}"
            join_code = secrets.token_urlsafe(JOIN_CODE_BYTES)
            crew = Crew(crew_id=crew_id, name=name, join_code=join_code)
            crew.add_member(owner_id)
            self._crews[crew_id] = crew
            self._event_store.append_command(
                event_type="crew.created",
                actor_id=owner_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={
                    "crew_id": crew_id,
                    "name": name,
                    "owner_id": owner_id,
                    "join_code": join_code,
                },
                idempotency_key=idempotency_key,
            )
            return crew

    def join_crew(
        self,
        *,
        crew_id: str,
        player_id: str,
        join_code: str,
        idempotency_key: str,
    ) -> Crew:
        with self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.type != "crew.member.joined":
                    raise ValueError("idempotency key conflict")
                return self._crews[existing.payload["crew_id"]]
            crew = self._crews[crew_id]
            if not secrets.compare_digest(crew.join_code, join_code):
                raise PermissionError("invalid join code")
            before = len(crew.member_ids)
            crew.add_member(player_id)
            if len(crew.member_ids) != before:
                self._event_store.append_command(
                    event_type="crew.member.joined",
                    actor_id=player_id,
                    visibility=EventVisibility.crews([crew_id]),
                    payload={"crew_id": crew_id, "player_id": player_id},
                    idempotency_key=idempotency_key,
                )
            return crew

    def is_member(self, *, crew_id: str, player_id: str) -> bool:
        with self._lock:
            crew = self._crews.get(crew_id)
            if crew is None:
                return False
            return player_id in crew.member_ids

    def has_crew(self, crew_id: str) -> bool:
        with self._lock:
            return crew_id in self._crews

    def summary(self, crew_id: str) -> dict:
        with self._lock:
            crew = self._crews[crew_id]
            return {
                "crew_id": crew.crew_id,
                "name": crew.name,
                "member_ids": list(crew.member_ids),
                "member_count": len(crew.member_ids),
                "ready_for_full_contracts": crew.ready_for_full_contracts,
                "readiness_warning": crew.readiness_warning,
            }

    def crew_ids_for_player(self, player_id: str) -> list[str]:
        with self._lock:
            return [
                crew_id
                for crew_id, crew in self._crews.items()
                if player_id in crew.member_ids
            ]

    def crew_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._crews)

    def member_ids(self, crew_id: str) -> list[str]:
        with self._lock:
            return list(self._crews[crew_id].member_ids)

    def _rebuild_from_events(self) -> None:
        for event in self._event_store.read():
            if event.type == "crew.created":
                crew = Crew(
                    crew_id=event.payload["crew_id"],
                    name=event.payload["name"],
                    join_code=event.payload["join_code"],
                )
                crew.add_member(event.payload["owner_id"])
                self._crews[crew.crew_id] = crew
            elif event.type == "crew.member.joined":
                self._crews[event.payload["crew_id"]].add_member(event.payload["player_id"])

    def _event_by_idempotency_key(self, idempotency_key: str):
        for event in self._event_store.read():
            if event.idempotency_key == idempotency_key:
                return event
        return None

    def _ensure_crew_create_replay_matches(self, event, *, owner_id: str, name: str) -> None:
        if event.type != "crew.created":
            raise ValueError("idempotency key conflict")
        if event.actor_id != owner_id or event.payload["name"] != name:
            raise ValueError("idempotency key conflict")


class ChatService:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        identity_service: IdentityService,
        crew_service: CrewService,
        artifact_service: ArtifactService | None = None,
    ):
        self._event_store = event_store
        self._identity_service = identity_service
        self._crew_service = crew_service
        self._artifact_service = artifact_service
        self._lock = threading.RLock()
        self._message_count = 0
        self._rebuild_from_events()

    def set_artifact_service(self, artifact_service: ArtifactService) -> None:
        self._artifact_service = artifact_service

    def send_direct(
        self,
        *,
        sender_player_id: str,
        recipient_player_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] = (),
    ) -> ChatMessage:
        if not self._identity_service.has_player(recipient_player_id):
            raise KeyError(recipient_player_id)
        normalized_artifact_ids = tuple(artifact_ids)
        self._validate_artifact_ids(
            sender_player_id=sender_player_id,
            artifact_ids=normalized_artifact_ids,
        )
        with self._lock:
            replay = self._matching_chat_replay(
                idempotency_key=idempotency_key,
                kind="direct",
                sender_player_id=sender_player_id,
                body=body,
                recipient_player_id=recipient_player_id,
                artifact_ids=normalized_artifact_ids,
            )
            if replay is not None:
                return replay
            message = self._new_message(
                kind="direct",
                sender_player_id=sender_player_id,
                recipient_player_id=recipient_player_id,
                body=body,
                artifact_ids=normalized_artifact_ids,
            )
            self._event_store.append_command(
                event_type="chat.message.created",
                actor_id=sender_player_id,
                visibility=EventVisibility.players([sender_player_id, recipient_player_id]),
                payload=message.__dict__,
                idempotency_key=idempotency_key,
            )
            return message

    def send_crew(
        self,
        *,
        sender_player_id: str,
        crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] = (),
    ) -> ChatMessage:
        if not self._crew_service.is_member(crew_id=crew_id, player_id=sender_player_id):
            raise PermissionError(crew_id)
        normalized_artifact_ids = tuple(artifact_ids)
        self._validate_artifact_ids(
            sender_player_id=sender_player_id,
            artifact_ids=normalized_artifact_ids,
        )
        with self._lock:
            replay = self._matching_chat_replay(
                idempotency_key=idempotency_key,
                kind="crew",
                sender_player_id=sender_player_id,
                body=body,
                sender_crew_id=crew_id,
                artifact_ids=normalized_artifact_ids,
            )
            if replay is not None:
                return replay
            message = self._new_message(
                kind="crew",
                sender_player_id=sender_player_id,
                sender_crew_id=crew_id,
                body=body,
                artifact_ids=normalized_artifact_ids,
            )
            self._event_store.append_command(
                event_type="chat.message.created",
                actor_id=sender_player_id,
                visibility=EventVisibility.crews([crew_id]),
                payload=message.__dict__,
                idempotency_key=idempotency_key,
            )
            return message

    def send_crew_to_crew(
        self,
        *,
        sender_player_id: str,
        sender_crew_id: str,
        recipient_crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] = (),
    ) -> ChatMessage:
        if not self._crew_service.is_member(crew_id=sender_crew_id, player_id=sender_player_id):
            raise PermissionError(sender_crew_id)
        if not self._crew_service.has_crew(recipient_crew_id):
            raise KeyError(recipient_crew_id)
        normalized_artifact_ids = tuple(artifact_ids)
        self._validate_artifact_ids(
            sender_player_id=sender_player_id,
            artifact_ids=normalized_artifact_ids,
        )
        with self._lock:
            replay = self._matching_chat_replay(
                idempotency_key=idempotency_key,
                kind="crew_to_crew",
                sender_player_id=sender_player_id,
                body=body,
                sender_crew_id=sender_crew_id,
                recipient_crew_id=recipient_crew_id,
                artifact_ids=normalized_artifact_ids,
            )
            if replay is not None:
                return replay
            message = self._new_message(
                kind="crew_to_crew",
                sender_player_id=sender_player_id,
                sender_crew_id=sender_crew_id,
                recipient_crew_id=recipient_crew_id,
                body=body,
                artifact_ids=normalized_artifact_ids,
            )
            self._event_store.append_command(
                event_type="chat.message.created",
                actor_id=sender_player_id,
                visibility=EventVisibility.crews([sender_crew_id, recipient_crew_id]),
                payload=message.__dict__,
                idempotency_key=idempotency_key,
            )
            self._append_chat_rumor_if_needed(
                message=message,
                idempotency_key=idempotency_key,
            )
            return message

    def _new_message(self, **kwargs) -> ChatMessage:
        self._message_count += 1
        return ChatMessage(message_id=f"msg_{self._message_count:06d}", **kwargs)

    def _append_chat_rumor_if_needed(
        self,
        *,
        message: ChatMessage,
        idempotency_key: str,
    ) -> None:
        if message.kind != "crew_to_crew":
            return
        leak_vector = self._chat_artifact_leak_vector(message)
        if leak_vector is None:
            return
        participant_crew_ids = {
            message.sender_crew_id,
            message.recipient_crew_id,
        }
        bystander_crew_ids = [
            crew_id
            for crew_id in self._crew_service.crew_ids()
            if crew_id not in participant_crew_ids
        ]
        if not bystander_crew_ids:
            return
        self._event_store.append_command(
            event_type="contract.rumor.leaked",
            actor_id="server",
            visibility=EventVisibility.crews(bystander_crew_ids),
            payload={
                "rumor_id": f"rumor_{message.message_id}",
                "source_type": "chat.message.created",
                "source_id": message.message_id,
                "conversation_scope": "crew_to_crew",
                "suspected_crew_ids": [
                    message.sender_crew_id,
                    message.recipient_crew_id,
                ],
                "summary": "A private artifact discussion is echoing between crews.",
                "pressure": "artifact_reference_detected",
                "leak_vector": leak_vector,
            },
            idempotency_key=f"{idempotency_key}.rumor",
        )

    def _chat_artifact_leak_vector(self, message: ChatMessage) -> str | None:
        if message.artifact_ids:
            return "artifact_attachment"
        if self._body_mentions_visible_artifact(message):
            return "artifact_name_mention"
        return None

    def _body_mentions_visible_artifact(self, message: ChatMessage) -> bool:
        if self._artifact_service is None:
            return False
        sender_crew_ids = self._crew_service.crew_ids_for_player(message.sender_player_id)
        visible = self._artifact_service.visible_artifacts_for_player(
            message.sender_player_id,
            crew_ids=sender_crew_ids,
        )
        normalized_body = _normalize_search_text(message.body)
        normalized_body_with_ids = f" {normalized_body} "
        for artifact in visible.get("artifacts", []):
            artifact_id = str(artifact.get("artifact_id", ""))
            if artifact_id and artifact_id.casefold() in message.body.casefold():
                return True
            title = _normalize_search_text(str(artifact.get("title", "")))
            if title and f" {title} " in normalized_body_with_ids:
                return True
        return False

    def _matching_chat_replay(self, *, idempotency_key: str, **expected) -> ChatMessage | None:
        for event in self._event_store.read():
            if event.idempotency_key != idempotency_key:
                continue
            if event.type != "chat.message.created":
                raise ValueError("idempotency key conflict")
            message = ChatMessage(**event.payload)
            for key, value in expected.items():
                if getattr(message, key) != value:
                    raise ValueError("idempotency key conflict")
            return message
        return None

    def _validate_artifact_ids(
        self,
        *,
        sender_player_id: str,
        artifact_ids: tuple[str, ...],
    ) -> None:
        if not artifact_ids:
            return
        if self._artifact_service is None:
            raise KeyError(artifact_ids[0])
        sender_crew_ids = self._crew_service.crew_ids_for_player(sender_player_id)
        for artifact_id in artifact_ids:
            self._artifact_service.inspect_artifact(
                artifact_id=artifact_id,
                player_id=sender_player_id,
                crew_ids=sender_crew_ids,
            )

    def _rebuild_from_events(self) -> None:
        for event in self._event_store.read():
            if event.type != "chat.message.created":
                continue
            message_id = event.payload["message_id"]
            if message_id.startswith("msg_"):
                self._message_count = max(self._message_count, int(message_id.removeprefix("msg_")))


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()


class VisibilityService:
    def __init__(self, *, event_store: JsonlEventStore, crew_service: CrewService):
        self._event_store = event_store
        self._crew_service = crew_service

    def visible_events_for_player(self, player_id: str):
        visible = {
            event.event_id: event
            for event in self._event_store.read_for_principal(Principal.player(player_id))
        }
        for crew_id in self._crew_service.crew_ids_for_player(player_id):
            for event in self._event_store.read_for_principal(Principal.crew(crew_id)):
                visible[event.event_id] = event
        return sorted(visible.values(), key=lambda event: event.sequence)


class ContractService:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        resolution_oracle: ResolutionOracle | None = None,
        artifact_service: ArtifactService | None = None,
    ):
        self._event_store = event_store
        self._resolution_oracle = (
            resolution_oracle
            if resolution_oracle is not None
            else DeterministicResolutionOracle()
        )
        self._artifact_service = artifact_service
        self._lock = threading.RLock()
        self._seed_starter_contract()

    def set_artifact_service(self, artifact_service: ArtifactService) -> None:
        self._artifact_service = artifact_service

    def board_for_player(self, player_id: str):
        _ = player_id
        return contract_board_from_events(self._event_store.read())

    def inbox_for_player(self, player_id: str):
        return inbox_from_board(player_id=player_id, board=self.board_for_player(player_id))

    def activate_contract_seed(
        self,
        *,
        seed: ContractSeed,
        actor_id: str,
        idempotency_key: str,
    ) -> dict:
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "contract.lifecycle.changed"
                    or existing.actor_id != actor_id
                    or existing.payload["contract_id"] != seed.contract.contract_id
                    or existing.payload["status"] != "active"
                ):
                    raise ValueError("idempotency key conflict")
                if not self._activation_seed_payload_matches(
                    seed=seed,
                    idempotency_key=idempotency_key,
                ):
                    raise ValueError("idempotency key conflict")
                return {
                    "contract_id": seed.contract.contract_id,
                    "lifecycle_status": "active",
                }
            self._validate_arc_previous_contract(seed.contract)
            self._validate_completed_contract_unlock_targets(seed)
            self._event_store.append_command(
                event_type="campaign.seeded",
                actor_id=actor_id,
                visibility=EventVisibility.public(),
                payload=seed.campaign.model_dump(mode="json"),
                idempotency_key=f"{idempotency_key}.campaign",
            )
            self._event_store.append_command(
                event_type="contract.hidden_truth.seeded",
                actor_id=actor_id,
                visibility=EventVisibility.server_only(),
                payload={
                    **seed.hidden_truth.model_dump(mode="json"),
                    "contract_id": seed.contract.contract_id,
                },
                idempotency_key=f"{idempotency_key}.hidden-truth",
            )
            self._event_store.append_command(
                event_type="artifact.graph.seeded",
                actor_id=actor_id,
                visibility=EventVisibility.server_only(),
                payload={
                    "graph": seed.artifact_graph.model_dump(mode="json"),
                    "public_artifact_ids": list(seed.public_artifact_ids),
                    "scoring_hints": seed.scoring_hints,
                    "phase_rewards": [
                        reward.model_dump(mode="json") for reward in seed.phase_rewards
                    ],
                    "unlock_requirements": [
                        requirement.model_dump(mode="json")
                        for requirement in seed.unlock_requirements
                    ],
                },
                idempotency_key=f"{idempotency_key}.artifact-graph",
            )
            self._event_store.append_command(
                event_type="contract.board.published",
                actor_id=actor_id,
                visibility=EventVisibility.public(),
                payload=seed.contract.model_dump(mode="json"),
                idempotency_key=f"{idempotency_key}.board",
            )
            self._event_store.append_command(
                event_type="contract.lifecycle.changed",
                actor_id=actor_id,
                visibility=EventVisibility.public(),
                payload={
                    "contract_id": seed.contract.contract_id,
                    "status": "active",
                    "previous_status": "draft",
                },
                idempotency_key=idempotency_key,
            )
            return {
                "contract_id": seed.contract.contract_id,
                "lifecycle_status": "active",
            }

    def archive_contract(
        self,
        *,
        contract_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> dict:
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            self._contract_by_id(contract_id)
            current_status = self._contract_lifecycle_status(contract_id)
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "contract.lifecycle.changed"
                    or existing.actor_id != actor_id
                    or existing.payload["contract_id"] != contract_id
                    or existing.payload["status"] != "archived"
                ):
                    raise ValueError("idempotency key conflict")
                return {
                    "contract_id": contract_id,
                    "lifecycle_status": "archived",
                }
            if current_status != "archived":
                self._event_store.append_command(
                    event_type="contract.lifecycle.changed",
                    actor_id=actor_id,
                    visibility=EventVisibility.public(),
                    payload={
                        "contract_id": contract_id,
                        "status": "archived",
                        "previous_status": current_status,
                    },
                    idempotency_key=idempotency_key,
                )
            return {
                "contract_id": contract_id,
                "lifecycle_status": "archived",
            }

    def lock_auction_preview(
        self,
        *,
        contract_id: str,
        actor_id: str,
        hours_elapsed: int,
        idempotency_key: str,
    ) -> dict:
        contract = self._contract_by_id(contract_id)
        phase_name = contract.phase.name
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "contract.phase.resolved"
                    or existing.actor_id != actor_id
                    or existing.payload["contract_id"] != contract_id
                    or existing.payload["phase"] != phase_name
                    or existing.payload["hours_elapsed"] != hours_elapsed
                ):
                    raise ValueError("idempotency key conflict")
                self._record_auction_preview_legacy_deltas(
                    contract=contract,
                    phase=phase_name,
                    reveal=existing.payload["reveal"],
                )
                return existing.payload["reveal"]
            resolved = self._resolved_auction_preview(
                contract_id=contract_id,
                phase=phase_name,
            )
            if resolved is not None:
                self._award_auction_preview_phase_rewards(
                    contract_id=contract_id,
                    phase=phase_name,
                    reveal=resolved,
                )
                self._record_auction_preview_legacy_deltas(
                    contract=contract,
                    phase=phase_name,
                    reveal=resolved,
                )
                return resolved
            if (
                hours_elapsed < contract.phase.remaining_hours
                and self._meaningful_action_count(contract_id=contract_id, phase=phase_name) < 2
            ):
                raise ValueError("phase still active")
            locked = self._locked_auction_preview(
                contract_id=contract_id,
                phase=phase_name,
            )
            lock_hours_elapsed = hours_elapsed
            if locked is None:
                self._event_store.append_command(
                    event_type="contract.phase.locked",
                    actor_id="server",
                    visibility=EventVisibility.public(),
                    payload={
                        "contract_id": contract_id,
                        "phase": phase_name,
                        "hours_elapsed": hours_elapsed,
                    },
                    idempotency_key=f"phase-lock.{contract_id}.auction-preview",
                )
            else:
                lock_hours_elapsed = locked["hours_elapsed"]
            reveal = self._build_auction_preview_reveal(
                contract_id=contract_id,
                phase=phase_name,
            )
            self._event_store.append_command(
                event_type="contract.phase.resolved",
                actor_id=actor_id,
                visibility=EventVisibility.public(),
                payload={
                    "contract_id": contract_id,
                    "phase": phase_name,
                    "hours_elapsed": lock_hours_elapsed,
                    "reveal": reveal,
                },
                idempotency_key=idempotency_key,
            )
            self._award_auction_preview_phase_rewards(
                contract_id=contract_id,
                phase=phase_name,
                reveal=reveal,
            )
            self._record_auction_preview_legacy_deltas(
                contract=contract,
                phase=phase_name,
                reveal=reveal,
            )
            return reveal

    def _seed_starter_contract(self) -> None:
        with self._lock:
            self._event_store.append_command(
                event_type="campaign.seeded",
                actor_id="server",
                visibility=EventVisibility.public(),
                payload=STARTER_CAMPAIGN.model_dump(mode="json"),
                idempotency_key=f"seed.{STARTER_CAMPAIGN.campaign_id}",
            )
            self._event_store.append_command(
                event_type="contract.hidden_truth.seeded",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload=STARTER_HIDDEN_TRUTH.model_dump(mode="json"),
                idempotency_key=f"seed.{STARTER_HIDDEN_TRUTH.truth_id}",
            )
            self._event_store.append_command(
                event_type="contract.board.published",
                actor_id="server",
                visibility=EventVisibility.public(),
                payload=STARTER_CONTRACT.model_dump(mode="json"),
                idempotency_key=f"seed.{STARTER_CONTRACT.contract_id}.board",
            )

    def _event_by_idempotency_key(self, idempotency_key: str):
        for event in self._event_store.read():
            if event.idempotency_key == idempotency_key:
                return event
        return None

    def _validate_arc_previous_contract(self, contract: Contract) -> None:
        if contract.arc is None or contract.arc.previous_contract_id is None:
            return
        for event in self._event_store.read():
            if event.type != "contract.board.published":
                continue
            published = Contract.model_validate(event.payload)
            if (
                published.contract_id == contract.arc.previous_contract_id
                and published.campaign_id == contract.campaign_id
            ):
                return
        raise ValueError(
            "arc previous contract must reference an existing contract in the same campaign"
        )

    def _validate_completed_contract_unlock_targets(self, seed: ContractSeed) -> None:
        required_contract_ids = {
            requirement.required_contract_id
            for requirement in seed.unlock_requirements
            if requirement.metric == "completed_contract"
        }
        if not required_contract_ids:
            return
        published_contracts = [
            Contract.model_validate(event.payload)
            for event in self._event_store.read()
            if event.type == "contract.board.published"
        ]
        for required_contract_id in required_contract_ids:
            if any(
                published.contract_id == required_contract_id
                and published.campaign_id == seed.contract.campaign_id
                for published in published_contracts
            ):
                continue
            raise ValueError(
                "completed_contract unlock must reference an existing contract in the same campaign"
            )

    def _activation_seed_payload_matches(
        self,
        *,
        seed: ContractSeed,
        idempotency_key: str,
    ) -> bool:
        expected = {
            f"{idempotency_key}.campaign": seed.campaign.model_dump(mode="json"),
            f"{idempotency_key}.hidden-truth": {
                **seed.hidden_truth.model_dump(mode="json"),
                "contract_id": seed.contract.contract_id,
            },
            f"{idempotency_key}.artifact-graph": {
                "graph": seed.artifact_graph.model_dump(mode="json"),
                "public_artifact_ids": list(seed.public_artifact_ids),
                "scoring_hints": seed.scoring_hints,
                "phase_rewards": [
                    reward.model_dump(mode="json") for reward in seed.phase_rewards
                ],
                "unlock_requirements": [
                    requirement.model_dump(mode="json")
                    for requirement in seed.unlock_requirements
                ],
            },
            f"{idempotency_key}.board": seed.contract.model_dump(mode="json"),
        }
        events_by_key = {
            event.idempotency_key: event
            for event in self._event_store.read()
            if event.idempotency_key in expected
        }
        for key, payload in expected.items():
            event = events_by_key.get(key)
            if event is None or event.payload != payload:
                return False
        return True

    def _contract_lifecycle_status(self, contract_id: str) -> str:
        status = "active"
        for event in self._event_store.read():
            if (
                event.type == "contract.lifecycle.changed"
                and event.payload["contract_id"] == contract_id
            ):
                status = event.payload["status"]
        return status

    def _resolved_auction_preview(self, *, contract_id: str, phase: str) -> dict | None:
        for event in self._event_store.read():
            if (
                event.type in {"contract.phase.locked", "contract.phase.resolved"}
                and event.payload["contract_id"] == contract_id
                and event.payload["phase"] == phase
            ):
                if event.type == "contract.phase.locked":
                    continue
                return event.payload["reveal"]
        return None

    def _award_auction_preview_phase_rewards(
        self,
        *,
        contract_id: str,
        phase: str,
        reveal: dict,
    ) -> None:
        if self._artifact_service is None:
            return
        standings = reveal.get("standings", [])
        if not standings:
            return
        leader_crew_id = standings[0]["crew_id"]
        rewards = self._phase_rewards_for_contract(contract_id)
        if not rewards and contract_id == STARTER_CONTRACT.contract_id:
            starter_reward_artifact_id = auction_preview_phase_reward_artifact_id(reveal)
            rewards = (
                PhaseReward(
                    phase=phase,
                    trigger="phase_resolved",
                    award_to="standing_leader",
                    artifact_id=starter_reward_artifact_id,
                    reason="Leader follow-up from auction preview resolution.",
                ),
            ) if starter_reward_artifact_id is not None else ()
        for reward in rewards:
            if reward.phase != phase or reward.trigger != "phase_resolved":
                continue
            if reward.award_to != "standing_leader":
                continue
            self._award_phase_reward_artifact(
                contract_id=contract_id,
                phase=phase,
                crew_id=leader_crew_id,
                artifact_id=reward.artifact_id,
                reason=reward.reason,
            )

    def _record_auction_preview_legacy_deltas(
        self,
        *,
        contract: Contract,
        phase: str,
        reveal: dict,
    ) -> None:
        phase_key = re.sub(r"[^a-z0-9]+", "-", phase.casefold()).strip("-")
        for standing in reveal.get("standings", []):
            delta = legacy_delta_for_standing(
                contract_id=contract.contract_id,
                contract_title=contract.title,
                phase=phase,
                standing=standing,
            )
            self._event_store.append_command(
                event_type="crew.legacy.delta.recorded",
                actor_id="server",
                visibility=EventVisibility.public(),
                payload=delta,
                idempotency_key=(
                    f"crew-legacy-delta.{contract.contract_id}."
                    f"{phase_key}.{delta['crew_id']}"
                ),
            )

    def _award_phase_reward_artifact(
        self,
        *,
        contract_id: str,
        phase: str,
        crew_id: str,
        artifact_id: str,
        reason: str,
    ) -> None:
        if self._crew_has_artifact_signal(
            crew_id=crew_id,
            artifact_id=artifact_id,
        ):
            return
        phase_key = re.sub(r"[^a-z0-9]+", "-", phase.casefold()).strip("-")
        reward_key = (
            f"artifact.phase-reward.{contract_id}.{phase_key}."
            f"{crew_id}.{artifact_id}"
        )
        self._event_store.append_command(
            event_type="artifact.phase_reward.awarded",
            actor_id="server",
            visibility=EventVisibility.crews([crew_id]),
            payload={
                "contract_id": contract_id,
                "phase": phase,
                "crew_id": crew_id,
                "artifact_id": artifact_id,
                "reason": reason,
            },
            idempotency_key=reward_key,
        )
        self._artifact_service.grant_artifact_access(
            artifact_id=artifact_id,
            actor_id="server",
            player_ids=[],
            crew_ids=[crew_id],
            reason=reason,
            idempotency_key=f"{reward_key}.grant",
        )

    def _crew_has_artifact_signal(self, *, crew_id: str, artifact_id: str) -> bool:
        for event in self._event_store.read_for_principal(Principal.crew(crew_id)):
            if event.type == "artifact.access.granted" and event.payload["artifact_id"] == artifact_id:
                return True
            if event.type == "artifact.dossier.cited" and event.payload["artifact_id"] == artifact_id:
                return True
        return False

    def _locked_auction_preview(self, *, contract_id: str, phase: str) -> dict | None:
        for event in self._event_store.read():
            if (
                event.type == "contract.phase.locked"
                and event.payload["contract_id"] == contract_id
                and event.payload["phase"] == phase
            ):
                return event.payload
        return None

    def _completed_auction_preview_oracle_audit(self, *, contract_id: str, phase: str):
        for event in reversed(self._event_store.read()):
            if (
                event.type == "oracle.resolution.completed"
                and event.payload["contract_id"] == contract_id
                and event.payload["phase"] == phase
            ):
                return event
        return None

    def _failed_auction_preview_oracle_audit(self, *, contract_id: str, phase: str):
        for event in reversed(self._event_store.read()):
            if (
                event.type == "oracle.resolution.failed"
                and event.payload["contract_id"] == contract_id
                and event.payload["phase"] == phase
            ):
                return event
        return None

    def _build_auction_preview_reveal(self, *, contract_id: str, phase: str | None = None) -> dict:
        resolved_phase = phase or self._contract_by_id(contract_id).phase.name
        packet = self._build_auction_preview_packet(contract_id=contract_id, phase=resolved_phase)
        input_packet_hash = self._oracle_packet_hash(packet)
        attempted_provider = self._oracle_runtime_metadata()
        completed_audit = self._completed_auction_preview_oracle_audit(
            contract_id=contract_id,
            phase=resolved_phase,
        )
        if completed_audit is not None and completed_audit.payload.get("accepted_output") is not None:
            if completed_audit.payload.get("input_packet_hash") != input_packet_hash:
                raise ValueError("oracle completed audit hash mismatch")
            result = validate_auction_preview_result(
                packet=packet,
                result=AuctionPreviewOracleResult.model_validate(
                    completed_audit.payload["accepted_output"],
                ),
            )
            return self._auction_preview_reveal_from_oracle_result(
                contract_id=contract_id,
                phase=resolved_phase,
                result=result,
            )
        requested_audit_key = f"oracle.resolution.{contract_id}.auction-preview.requested"
        requested_audit = self._event_by_idempotency_key(requested_audit_key)
        if requested_audit is None:
            self._event_store.append_command(
                event_type="oracle.resolution.requested",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "audit_schema_version": 1,
                    "contract_id": contract_id,
                    "phase": resolved_phase,
                    "input_packet_hash": input_packet_hash,
                    "provider_attempted": attempted_provider.provider,
                    "model": attempted_provider.model,
                    "prompt_version": attempted_provider.prompt_version,
                    "validation_status": "not_started",
                },
                idempotency_key=requested_audit_key,
            )
        fallback = False
        fallback_reason: str | None = None
        failure_stage: str | None = None
        failure_provider = attempted_provider
        try:
            candidate = self._resolution_oracle.resolve_auction_preview(packet)
        except Exception as exc:
            fallback = True
            fallback_reason = exc.__class__.__name__
            failure_stage = "provider_call"
        else:
            failure_provider = candidate.provider
            try:
                result = validate_auction_preview_result(packet=packet, result=candidate)
            except Exception as exc:
                fallback = True
                fallback_reason = exc.__class__.__name__
                failure_stage = "server_validation"
        if fallback:
            assert fallback_reason is not None
            assert failure_stage is not None
            failed_audit = self._failed_auction_preview_oracle_audit(
                contract_id=contract_id,
                phase=resolved_phase,
            )
            if failed_audit is not None:
                fallback_reason = failed_audit.payload.get("fallback_reason") or fallback_reason
            else:
                self._event_store.append_command(
                    event_type="oracle.resolution.failed",
                    actor_id="server",
                    visibility=EventVisibility.server_only(),
                    payload={
                        "audit_schema_version": 1,
                        "contract_id": contract_id,
                        "phase": resolved_phase,
                        "input_packet_hash": input_packet_hash,
                        "provider_attempted": failure_provider.provider,
                        "model": failure_provider.model,
                        "prompt_version": failure_provider.prompt_version,
                        "validation_status": (
                            "rejected"
                            if failure_stage == "server_validation"
                            else "provider_error"
                        ),
                        "failure_stage": failure_stage,
                        "failure_type": fallback_reason,
                        "fallback": True,
                        "fallback_provider": "deterministic",
                        "fallback_reason": fallback_reason,
                    },
                    idempotency_key=f"oracle.resolution.{contract_id}.auction-preview.failed",
                )
            result = DeterministicResolutionOracle().resolve_auction_preview(packet)
        self._event_store.append_command(
            event_type="oracle.resolution.completed",
            actor_id="server",
            visibility=EventVisibility.server_only(),
            payload={
                "audit_schema_version": 1,
                "contract_id": contract_id,
                "phase": resolved_phase,
                "provider": result.provider.provider,
                "model": result.provider.model,
                "prompt_version": result.provider.prompt_version,
                "fallback": fallback,
                "fallback_reason": fallback_reason,
                "validation_status": "fallback_validated" if fallback else "validated",
                "crew_count": len(packet.crews),
                "standing_count": len(result.standings),
                "warning_count": len(result.validation_warnings),
                "input_packet_hash": input_packet_hash,
                "accepted_output_hash": self._oracle_result_hash(result),
                "accepted_output": result.model_dump(mode="json"),
            },
            idempotency_key=f"oracle.resolution.{contract_id}.auction-preview.completed",
        )
        return self._auction_preview_reveal_from_oracle_result(
            contract_id=contract_id,
            phase=resolved_phase,
            result=result,
        )

    def _build_auction_preview_packet(
        self,
        *,
        contract_id: str,
        phase: str | None = None,
    ) -> AuctionPreviewOraclePacket:
        contract = self._contract_by_id(contract_id)
        phase_name = phase or contract.phase.name
        hidden_truth = self._hidden_truth_for_contract(contract_id)
        graph = self._artifact_graph_for_contract(contract_id)
        scoring_hints = self._scoring_hints_for_contract(contract_id)
        score_inputs = self._auction_preview_score_inputs()
        allowed_evidence_ids = tuple(
            dict.fromkeys(
                (
                    STARTER_FRAGMENT.fragment_id,
                    *(
                        artifact.artifact_id
                        for artifact in graph.artifacts
                    ),
                    *(asset.asset_id for asset in contract.evidence_assets),
                    *(
                        evidence_id
                        for score_input in score_inputs
                        for evidence_id in score_input.evidence_ids
                    ),
                    *(
                        asset_id
                        for score_input in score_inputs
                        for asset_id in score_input.exposed_assets
                    ),
                )
            )
        )
        return AuctionPreviewOraclePacket(
            contract_id=contract_id,
            phase=phase_name,
            hidden_truth_summary=hidden_truth.summary,
            allowed_reveal_strings=tuple(
                scoring_hints.get(
                    "allowed_reveal_strings",
                    (
                        "Auction house provenance is now suspect.",
                        "Rival alternate clue paths remain open.",
                    ),
                )
            ),
            rubric_hooks=tuple(
                scoring_hints.get("rubric_hooks", contract.proof_dossier_needs)
            ),
            crews=tuple(
                AuctionPreviewCrewPacket(
                    crew_id=score_input.crew_id,
                    claim=score_input.claim,
                    reasoning=score_input.reasoning,
                    weaknesses=score_input.weaknesses,
                    provenance_concerns=score_input.provenance_concerns,
                    evidence_ids=tuple(score_input.evidence_ids),
                    artifact_citations=tuple(score_input.artifact_citations),
                    known_edges=tuple(score_input.known_edges),
                    exposed_assets=tuple(score_input.exposed_assets),
                    action_intents=tuple(score_input.action_intents),
                    crew_noise=score_input.crew_noise,
                )
                for score_input in score_inputs
            ),
            allowed_evidence_ids=allowed_evidence_ids,
            score_min=0,
            score_max=100,
        )

    def _contract_by_id(self, contract_id: str) -> Contract:
        for event in reversed(self._event_store.read()):
            if (
                event.type == "contract.board.published"
                and event.payload["contract_id"] == contract_id
            ):
                return Contract.model_validate(event.payload)
        raise KeyError(contract_id)

    def _hidden_truth_for_contract(self, contract_id: str) -> HiddenTruth:
        for event in reversed(self._event_store.read()):
            if event.type != "contract.hidden_truth.seeded":
                continue
            if event.payload.get("contract_id") == contract_id:
                return HiddenTruth.model_validate(event.payload)
            if (
                contract_id == STARTER_CONTRACT.contract_id
                and event.payload.get("truth_id") == STARTER_HIDDEN_TRUTH.truth_id
            ):
                return STARTER_HIDDEN_TRUTH
        if contract_id == STARTER_CONTRACT.contract_id:
            return STARTER_HIDDEN_TRUTH
        raise KeyError(contract_id)

    def _artifact_graph_for_contract(self, contract_id: str) -> ArtifactGraph:
        if self._artifact_service is not None:
            return self._artifact_service.graph_for_contract(contract_id)
        if contract_id == STARTER_CONTRACT.contract_id:
            return STARTER_ARTIFACT_GRAPH
        for event in reversed(self._event_store.read()):
            if event.type != "artifact.graph.seeded":
                continue
            payload = event.payload
            graph_payload = payload.get("graph", payload)
            graph = ArtifactGraph.model_validate(graph_payload)
            if graph.contract_id == contract_id:
                return graph
        raise KeyError(contract_id)

    def _scoring_hints_for_contract(self, contract_id: str) -> dict:
        for event in reversed(self._event_store.read()):
            if event.type != "artifact.graph.seeded":
                continue
            payload = event.payload
            graph_payload = payload.get("graph", payload)
            graph = ArtifactGraph.model_validate(graph_payload)
            if graph.contract_id == contract_id:
                return dict(payload.get("scoring_hints", {}))
        return {}

    def _phase_rewards_for_contract(self, contract_id: str) -> tuple[PhaseReward, ...]:
        for event in reversed(self._event_store.read()):
            if event.type != "artifact.graph.seeded":
                continue
            payload = event.payload
            graph_payload = payload.get("graph", payload)
            graph = ArtifactGraph.model_validate(graph_payload)
            if graph.contract_id == contract_id:
                return tuple(
                    PhaseReward.model_validate(reward)
                    for reward in payload.get("phase_rewards", ())
                )
        return ()

    def _auction_preview_reveal_from_oracle_result(
        self,
        *,
        contract_id: str,
        phase: str = "Auction Preview",
        result: AuctionPreviewOracleResult,
    ) -> dict:
        standings = [
            {
                "crew_id": standing.crew_id,
                "score": standing.score,
                "standing": standing.standing,
                "strengths": list(standing.strengths),
                "weaknesses": list(standing.weaknesses),
                "penalties": list(standing.penalties),
                "revealed_clues": list(standing.revealed_clues),
            }
            for standing in result.standings
        ]
        return {
            "contract_id": contract_id,
            "phase": phase,
            "status": "resolved",
            "standings": standings,
            "contract_state": list(result.contract_state),
            "narration": result.narration,
        }

    def _oracle_packet_hash(self, packet: AuctionPreviewOraclePacket) -> str:
        return hashlib.sha256(packet.model_dump_json().encode("utf-8")).hexdigest()

    def _oracle_result_hash(self, result: AuctionPreviewOracleResult) -> str:
        return hashlib.sha256(result.model_dump_json().encode("utf-8")).hexdigest()

    def _oracle_runtime_metadata(self) -> OracleProviderMetadata:
        metadata = getattr(self._resolution_oracle, "runtime_metadata", None)
        if callable(metadata):
            return OracleProviderMetadata.model_validate(metadata())
        return OracleProviderMetadata(
            provider="unknown",
            model=None,
            prompt_version="unknown",
        )

    def _auction_preview_score_inputs(self) -> list[AuctionPreviewScoreInput]:
        crew_ids = self._crew_ids()
        actions_by_crew = self._current_actions_by_crew()
        score_inputs: list[AuctionPreviewScoreInput] = []
        for crew_id in crew_ids:
            dossier = self._current_dossier_for_scoring(crew_id)
            citation_artifact_ids = tuple(
                citation["artifact_id"] for citation in dossier.artifact_citations
            )
            known_edges = self._known_edges_for_artifacts(citation_artifact_ids)
            evidence_ids = tuple(dict.fromkeys((*dossier.evidence_ids, *citation_artifact_ids)))
            citation_reasoning = "\n".join(
                f"{citation['artifact_id']}: {citation['claim']}"
                for citation in dossier.artifact_citations
            )
            reasoning = "\n".join(
                part for part in (dossier.reasoning, citation_reasoning) if part
            )
            citation_quotes = "\n".join(
                f"{citation['artifact_id']}: {citation['quote']}"
                for citation in dossier.artifact_citations
            )
            provenance_concerns = "\n".join(
                part for part in (dossier.provenance_concerns, citation_quotes) if part
            )
            submitted_actions = [
                action
                for action in actions_by_crew.get(crew_id, [])
                if action["status"] == "submitted"
            ]
            score_inputs.append(
                AuctionPreviewScoreInput(
                    crew_id=crew_id,
                    claim=dossier.claim,
                    evidence_ids=evidence_ids,
                    reasoning=reasoning,
                    weaknesses=dossier.weaknesses,
                    provenance_concerns=provenance_concerns,
                    artifact_citations=dossier.artifact_citations,
                    known_edges=known_edges,
                    exposed_assets=tuple(
                        dict.fromkeys(
                            (
                                *evidence_ids,
                                *(
                                    asset
                                    for action in submitted_actions
                                    for asset in action["exposed_assets"]
                                ),
                            )
                        )
                    ),
                    action_intents=[action["intent"] for action in submitted_actions],
                    crew_noise=sum(action["crew_noise_impact"] for action in submitted_actions),
                )
            )
        return score_inputs

    def _known_edges_for_artifacts(self, artifact_ids: tuple[str, ...]) -> tuple[dict, ...]:
        if len(artifact_ids) < 2:
            return ()
        known_edges: list[dict] = []
        graphs = (
            self._artifact_service.seeded_graphs().values()
            if self._artifact_service is not None
            else ((STARTER_ARTIFACT_GRAPH, ()),)
        )
        for graph, _ in graphs:
            visible = graph.visible_slice(set(artifact_ids))
            known_edges.extend(visible["edges"])
        return tuple(known_edges)

    def _current_dossier_for_scoring(self, crew_id: str) -> ProofDossier:
        current: ProofDossier | None = None
        for event in self._event_store.read_for_principal(Principal.crew(crew_id)):
            if event.type == "crew.created" and current is None:
                current = ProofDossier.empty(
                    dossier_id=f"dossier_{crew_id}",
                    crew_id=crew_id,
                    packet_lead_player_id=event.payload["owner_id"],
                )
            elif event.type in {
                "proof.dossier.framing.updated",
                "proof.dossier.contribution.added",
                "artifact.dossier.cited",
                "proof.packet_lead.replaced",
            }:
                current = ProofDossier.model_validate(event.payload["dossier"])
        if current is None:
            raise KeyError(crew_id)
        return current

    def _current_actions_by_crew(self) -> dict[str, list[dict]]:
        latest: dict[str, dict] = {}
        for event in self._event_store.read():
            if event.type not in {"action.submitted", "action.edited", "action.canceled"}:
                continue
            action = event.payload["action"]
            latest[action["action_id"]] = action
        by_crew: dict[str, list[dict]] = {}
        for action in latest.values():
            by_crew.setdefault(action["crew_id"], []).append(action)
        return by_crew

    def _meaningful_action_count(self, *, contract_id: str, phase: str) -> int:
        return sum(
            1
            for actions in self._current_actions_by_crew().values()
            for action in actions
            if action["status"] == "submitted"
            and self._is_meaningful_auction_preview_action(
                action,
                contract_id=contract_id,
                phase=phase,
            )
        )

    def _is_meaningful_auction_preview_action(
        self,
        action: dict,
        *,
        contract_id: str,
        phase: str,
    ) -> bool:
        exposed_assets = set(action["exposed_assets"])
        if exposed_assets & {"fragment_starter_ledger", "asset_door_omen"}:
            return True
        graph = self._artifact_graph_for_contract(contract_id)
        if self._artifact_service is not None:
            visible = set(self._artifact_service.seeded_graphs()[contract_id][1])
        else:
            visible = set(STARTER_PUBLIC_ARTIFACT_IDS)
        return bool(
            action_unlock_candidates(
                graph=graph,
                contract_id=contract_id,
                phase=phase,
                intent=action["intent"],
                exposed_assets=action.get("exposed_assets", ()),
                already_visible_artifact_ids=visible,
            )
        )

    def _crew_ids(self) -> list[str]:
        crew_ids = [
            event.payload["crew_id"]
            for event in self._event_store.read()
            if event.type == "crew.created"
        ]
        return sorted(dict.fromkeys(crew_ids))


class ProofService:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        identity_service: IdentityService,
        crew_service: CrewService,
        artifact_service: ArtifactService | None = None,
    ):
        self._event_store = event_store
        self._identity_service = identity_service
        self._crew_service = crew_service
        self._artifact_service = artifact_service
        self._lock = threading.RLock()
        self._seed_starter_fragment()

    def set_artifact_service(self, artifact_service: ArtifactService) -> None:
        self._artifact_service = artifact_service

    def fragment_for_player(self, *, fragment_id: str, player_id: str) -> dict:
        fragment = self._visible_fragment(fragment_id=fragment_id, player_id=player_id)
        if fragment is None:
            raise KeyError(fragment_id)
        return fragment.surface_view()

    def transfer_fragment(
        self,
        *,
        fragment_id: str,
        sender_player_id: str,
        recipient_player_id: str,
        idempotency_key: str,
    ) -> dict:
        if not self._identity_service.has_player(recipient_player_id):
            raise KeyError(recipient_player_id)
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                self._ensure_transfer_matches(
                    existing,
                    sender_player_id=sender_player_id,
                    recipient_player_id=recipient_player_id,
                    fragment_id=fragment_id,
                )
                return existing.payload["surface"]
            fragment = self._visible_fragment(
                fragment_id=fragment_id,
                player_id=sender_player_id,
            )
            if fragment is None:
                raise KeyError(fragment_id)
            copied = fragment.copy_for_transfer(
                new_fragment_id=f"{fragment_id}.copy.{recipient_player_id}.{self._next_transfer_number()}",
                sender_player_id=sender_player_id,
                recipient_player_id=recipient_player_id,
            )
            surface = copied.surface_view()
            self._event_store.append_command(
                event_type="proof.fragment.transferred",
                actor_id=sender_player_id,
                visibility=EventVisibility.players([sender_player_id, recipient_player_id]),
                payload={
                    "sender_player_id": sender_player_id,
                    "recipient_player_id": recipient_player_id,
                    "source_fragment_id": fragment_id,
                    "surface": surface,
                },
                idempotency_key=idempotency_key,
            )
            self._event_store.append_command(
                event_type="proof.fragment.transferred.internal",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "transfer_idempotency_key": idempotency_key,
                    "fragment": copied.model_dump(mode="json"),
                },
                idempotency_key=f"{idempotency_key}.internal",
            )
            return surface

    def check_provenance(
        self,
        *,
        fragment_id: str,
        player_id: str,
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "proof.provenance.checked"
                    or existing.actor_id != player_id
                    or existing.payload["fragment_id"] != fragment_id
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["result"]
            if self._side_actions_used(player_id) >= SIDE_ACTION_LIMIT_PER_PHASE:
                raise ValueError("side action limit reached")
            fragment = self._visible_fragment(fragment_id=fragment_id, player_id=player_id)
            if fragment is None:
                raise KeyError(fragment_id)
            result = fragment.checked_view()
            self._event_store.append_command(
                event_type="proof.provenance.checked",
                actor_id=player_id,
                visibility=EventVisibility.players([player_id]),
                payload={"fragment_id": fragment_id, "result": result},
                idempotency_key=idempotency_key,
            )
            return result

    def _seed_starter_fragment(self) -> None:
        self._event_store.append_command(
            event_type="proof.fragment.seeded",
            actor_id="server",
            visibility=EventVisibility.server_only(),
            payload=STARTER_FRAGMENT.model_dump(mode="json"),
            idempotency_key=f"seed.{STARTER_FRAGMENT.fragment_id}",
        )

    def _fragment_with_provenance(self, fragment_id: str) -> ProofFragment:
        if fragment_id == STARTER_FRAGMENT.fragment_id:
            return STARTER_FRAGMENT
        for event in self._event_store.read():
            if event.type == "proof.fragment.seeded" and event.payload["fragment_id"] == fragment_id:
                return ProofFragment.model_validate(event.payload)
            if (
                event.type == "proof.fragment.transferred.internal"
                and event.payload["fragment"]["fragment_id"] == fragment_id
            ):
                return ProofFragment.model_validate(event.payload["fragment"])
        raise KeyError(fragment_id)

    def _visible_fragment(self, *, fragment_id: str, player_id: str) -> ProofFragment | None:
        if fragment_id == STARTER_FRAGMENT.fragment_id and self._owns_starter_fragment(player_id):
            return STARTER_FRAGMENT
        for event in self._event_store.read_for_principal(Principal.player(player_id)):
            if event.type != "proof.fragment.transferred":
                continue
            if event.payload["surface"]["fragment_id"] == fragment_id:
                return self._fragment_with_provenance(fragment_id)
        return None

    def _owns_starter_fragment(self, player_id: str) -> bool:
        for event in self._event_store.read():
            if event.type == "identity.player.registered" and event.payload["player_id"] == player_id:
                return True
            if event.type == "identity.player.registered":
                return False
        return False

    def _next_transfer_number(self) -> int:
        return (
            sum(1 for event in self._event_store.read() if event.type == "proof.fragment.transferred")
            + 1
        )

    def _side_actions_used(self, player_id: str) -> int:
        return sum(
            1
            for event in self._event_store.read_for_principal(Principal.player(player_id))
            if event.type == "proof.provenance.checked" and event.actor_id == player_id
        )

    def _event_by_idempotency_key(self, idempotency_key: str):
        for event in self._event_store.read():
            if event.idempotency_key == idempotency_key:
                return event
        return None

    def _ensure_transfer_matches(
        self,
        event,
        *,
        sender_player_id: str,
        recipient_player_id: str,
        fragment_id: str,
    ) -> None:
        if event.type != "proof.fragment.transferred":
            raise ValueError("idempotency key conflict")
        if (
            event.actor_id != sender_player_id
            or event.payload["recipient_player_id"] != recipient_player_id
            or event.payload["source_fragment_id"] != fragment_id
        ):
            raise ValueError("idempotency key conflict")

    def dossier_for_crew(self, *, crew_id: str, player_id: str) -> dict:
        if not self._crew_service.is_member(crew_id=crew_id, player_id=player_id):
            raise PermissionError("not a crew member")
        return self._current_dossier(crew_id).model_dump(mode="json")

    def update_dossier_framing(
        self,
        *,
        crew_id: str,
        player_id: str,
        updates: dict,
        idempotency_key: str,
    ) -> dict:
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "proof.dossier.framing.updated"
                    or existing.actor_id != player_id
                    or existing.payload["crew_id"] != crew_id
                    or existing.payload["updates"] != updates
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["dossier"]
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            if not self._crew_service.is_member(crew_id=crew_id, player_id=player_id):
                raise PermissionError("not a crew member")
            dossier = self._current_dossier(crew_id)
            if dossier.packet_lead_player_id != player_id:
                raise PermissionError("packet lead only")
            updated = dossier.with_framing(**updates)
            self._event_store.append_command(
                event_type="proof.dossier.framing.updated",
                actor_id=player_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={
                    "crew_id": crew_id,
                    "updates": updates,
                    "dossier": updated.model_dump(mode="json"),
                },
                idempotency_key=idempotency_key,
            )
            return updated.model_dump(mode="json")

    def add_dossier_contribution(
        self,
        *,
        crew_id: str,
        player_id: str,
        note: str,
        evidence_ids: list[str],
        idempotency_key: str,
    ) -> dict:
        if not self._crew_service.is_member(crew_id=crew_id, player_id=player_id):
            raise PermissionError("not a crew member")
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "proof.dossier.contribution.added"
                    or existing.actor_id != player_id
                    or existing.payload["crew_id"] != crew_id
                    or existing.payload["note"] != note
                    or existing.payload["evidence_ids"] != evidence_ids
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["dossier"]
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            updated = self._current_dossier(crew_id).with_contribution(
                player_id=player_id,
                note=note,
                evidence_ids=evidence_ids,
            )
            self._event_store.append_command(
                event_type="proof.dossier.contribution.added",
                actor_id=player_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={
                    "crew_id": crew_id,
                    "note": note,
                    "evidence_ids": evidence_ids,
                    "dossier": updated.model_dump(mode="json"),
                },
                idempotency_key=idempotency_key,
            )
            return updated.model_dump(mode="json")

    def cite_artifact_in_dossier(
        self,
        *,
        crew_id: str,
        player_id: str,
        artifact_id: str,
        claim: str,
        quote: str,
        idempotency_key: str,
    ) -> dict:
        if not self._crew_service.is_member(crew_id=crew_id, player_id=player_id):
            raise PermissionError("not a crew member")
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "artifact.dossier.cited"
                    or existing.actor_id != player_id
                    or existing.payload["crew_id"] != crew_id
                    or existing.payload["artifact_id"] != artifact_id
                    or existing.payload["claim"] != claim
                    or existing.payload["quote"] != quote
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["dossier"]
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            if self._artifact_service is None:
                raise KeyError(artifact_id)
            self._artifact_service.inspect_artifact(
                artifact_id=artifact_id,
                player_id=player_id,
                crew_ids=self._crew_service.crew_ids_for_player(player_id),
            )
            updated = self._current_dossier(crew_id).with_artifact_citation(
                player_id=player_id,
                artifact_id=artifact_id,
                claim=claim,
                quote=quote,
            )
            self._event_store.append_command(
                event_type="artifact.dossier.cited",
                actor_id=player_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={
                    "crew_id": crew_id,
                    "artifact_id": artifact_id,
                    "claim": claim,
                    "quote": quote,
                    "dossier": updated.model_dump(mode="json"),
                },
                idempotency_key=idempotency_key,
            )
            return updated.model_dump(mode="json")

    def vote_packet_lead(
        self,
        *,
        crew_id: str,
        voter_player_id: str,
        candidate_player_id: str,
        idempotency_key: str,
    ) -> dict:
        if not self._crew_service.is_member(crew_id=crew_id, player_id=voter_player_id):
            raise PermissionError("not a crew member")
        if not self._crew_service.is_member(crew_id=crew_id, player_id=candidate_player_id):
            raise PermissionError("candidate not a crew member")
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "proof.packet_lead.vote.cast"
                    or existing.actor_id != voter_player_id
                    or existing.payload["crew_id"] != crew_id
                    or existing.payload["candidate_player_id"] != candidate_player_id
                ):
                    raise ValueError("idempotency key conflict")
                return self._current_dossier(crew_id).model_dump(mode="json")
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            self._event_store.append_command(
                event_type="proof.packet_lead.vote.cast",
                actor_id=voter_player_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={
                    "crew_id": crew_id,
                    "voter_player_id": voter_player_id,
                    "candidate_player_id": candidate_player_id,
                },
                idempotency_key=idempotency_key,
            )
            current = self._current_dossier(crew_id)
            winner = self._packet_lead_majority_winner(crew_id)
            if winner is not None and winner != current.packet_lead_player_id:
                current = current.with_packet_lead(winner)
                self._event_store.append_command(
                    event_type="proof.packet_lead.replaced",
                    actor_id="server",
                    visibility=EventVisibility.crews([crew_id]),
                    payload={"dossier": current.model_dump(mode="json")},
                    idempotency_key=f"packet-lead.replace.{crew_id}.{winner}.{self._replacement_count(crew_id) + 1}",
                )
            return current.model_dump(mode="json")

    def _current_dossier(self, crew_id: str) -> ProofDossier:
        current: ProofDossier | None = None
        for event in self._event_store.read_for_principal(Principal.crew(crew_id)):
            if event.type == "crew.created" and event.payload["crew_id"] == crew_id and current is None:
                current = ProofDossier.empty(
                    dossier_id=f"dossier_{crew_id}",
                    crew_id=crew_id,
                    packet_lead_player_id=event.payload["owner_id"],
                )
            elif event.type in {
                "proof.dossier.framing.updated",
                "proof.dossier.contribution.added",
                "artifact.dossier.cited",
                "proof.packet_lead.replaced",
            }:
                current = ProofDossier.model_validate(event.payload["dossier"])
        if current is None:
            raise KeyError(crew_id)
        return current

    def _packet_lead_majority_winner(self, crew_id: str) -> str | None:
        latest_votes: dict[str, str] = {}
        member_ids = set(self._crew_service.member_ids(crew_id))
        for event in self._event_store.read_for_principal(Principal.crew(crew_id)):
            if event.type != "proof.packet_lead.vote.cast":
                continue
            voter = event.payload["voter_player_id"]
            candidate = event.payload["candidate_player_id"]
            if voter in member_ids and candidate in member_ids:
                latest_votes[voter] = candidate
        threshold = (len(member_ids) // 2) + 1
        for candidate in sorted(member_ids):
            if list(latest_votes.values()).count(candidate) >= threshold:
                return candidate
        return None

    def _replacement_count(self, crew_id: str) -> int:
        return sum(
            1
            for event in self._event_store.read_for_principal(Principal.crew(crew_id))
            if event.type == "proof.packet_lead.replaced"
        )

    def _auction_preview_locked(self) -> bool:
        return any(
            event.type in {"contract.phase.locked", "contract.phase.resolved"}
            and event.payload["contract_id"] == STARTER_CONTRACT.contract_id
            and event.payload["phase"] == "Auction Preview"
            for event in self._event_store.read()
        )


class ActionService:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        crew_service: CrewService,
        artifact_service: ArtifactService | None = None,
    ):
        self._event_store = event_store
        self._crew_service = crew_service
        self._artifact_service = artifact_service
        self._lock = threading.RLock()

    def set_artifact_service(self, artifact_service: ArtifactService) -> None:
        if self._artifact_service is None:
            self._artifact_service = artifact_service

    def submit_action(
        self,
        *,
        player_id: str,
        crew_id: str,
        intent: str,
        confirmed: bool,
        rumor_id: str | None = None,
        rumor_response_mode: str = "investigate",
        responds_to_rumor_escalation: bool = False,
        rumor_escalation_mode: str | None = None,
        idempotency_key: str,
    ) -> dict:
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "action.submitted"
                    or existing.actor_id != player_id
                    or existing.payload["confirmed"] is not confirmed
                    or existing.payload["action"]["crew_id"] != crew_id
                    or existing.payload["action"]["intent"] != intent
                    or existing.payload["action"].get("responds_to_rumor_id") != rumor_id
                    or existing.payload["action"].get(
                        "rumor_response_mode",
                        "investigate",
                    )
                    != rumor_response_mode
                    or existing.payload["action"].get(
                        "responds_to_rumor_escalation",
                        False,
                    )
                    is not responds_to_rumor_escalation
                    or existing.payload["action"].get("rumor_escalation_mode")
                    != rumor_escalation_mode
                ):
                    raise ValueError("idempotency key conflict")
                if rumor_id is not None:
                    rumor = self._require_visible_rumor(crew_id=crew_id, rumor_id=rumor_id)
                    self._append_rumor_response_outcome(
                        player_id=player_id,
                        crew_id=crew_id,
                        action=existing.payload["action"],
                        rumor=rumor,
                        rumor_response_mode=rumor_response_mode,
                        idempotency_key=idempotency_key,
                    )
                if responds_to_rumor_escalation:
                    escalation = self._require_rumor_escalation(crew_id=crew_id)
                    self._append_rumor_escalation_outcome(
                        player_id=player_id,
                        crew_id=crew_id,
                        action=existing.payload["action"],
                        mode=rumor_escalation_mode or "integrate",
                        escalation=escalation,
                        idempotency_key=idempotency_key,
                    )
                self._award_action_artifacts(
                    action=existing.payload["action"],
                    player_id=player_id,
                    crew_id=crew_id,
                )
                return existing.payload["action"]
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            if not confirmed:
                raise ValueError("unconfirmed action was not submitted")
            if not self._crew_service.is_member(crew_id=crew_id, player_id=player_id):
                raise PermissionError(crew_id)
            if rumor_id is None and rumor_response_mode != "investigate":
                raise ValueError("rumor response mode requires rumor_id")
            if rumor_escalation_mode is not None and not responds_to_rumor_escalation:
                raise ValueError("rumor escalation mode requires escalation response")
            rumor: dict | None = None
            if rumor_id is not None:
                rumor = self._require_visible_rumor(crew_id=crew_id, rumor_id=rumor_id)
            escalation: dict | None = None
            if responds_to_rumor_escalation:
                escalation = self._require_rumor_escalation(crew_id=crew_id)
            action_number = self._submitted_action_count(crew_id) + 1
            frame = NormalizedAction.from_intent(
                intent=intent,
                actor_player_id=player_id,
                crew_id=crew_id,
                action_number=action_number,
            )
            action = {
                "action_id": f"action_{self._global_action_count() + 1:06d}",
                "status": "submitted",
                **frame.model_dump(mode="json"),
            }
            if rumor_id is not None:
                action["responds_to_rumor_id"] = rumor_id
                action["rumor_response_mode"] = rumor_response_mode
            if responds_to_rumor_escalation:
                action["responds_to_rumor_escalation"] = True
                action["rumor_escalation_mode"] = rumor_escalation_mode or "integrate"
            self._event_store.append_command(
                event_type="action.submitted",
                actor_id=player_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={"confirmed": confirmed, "action": action},
                idempotency_key=idempotency_key,
            )
            if rumor is not None:
                self._append_rumor_response_outcome(
                    player_id=player_id,
                    crew_id=crew_id,
                    action=action,
                    rumor=rumor,
                    rumor_response_mode=rumor_response_mode,
                    idempotency_key=idempotency_key,
                )
            if escalation is not None:
                self._append_rumor_escalation_outcome(
                    player_id=player_id,
                    crew_id=crew_id,
                    action=action,
                    mode=action["rumor_escalation_mode"],
                    escalation=escalation,
                    idempotency_key=idempotency_key,
                )
            self._award_action_artifacts(
                action=action,
                player_id=player_id,
                crew_id=crew_id,
            )
            return action

    def _require_rumor_escalation(self, *, crew_id: str) -> dict:
        memory = rumor_memory_from_events(
            crew_id=crew_id,
            events=self._event_store.read(),
        )
        assessment_counts = {
            str(assessment): int(count)
            for assessment, count in memory.get("assessment_counts", {}).items()
        }
        credible_count = sum(
            count
            for assessment, count in assessment_counts.items()
            if assessment.startswith("credible_")
        )
        if credible_count < 2:
            raise ValueError("rumor escalation requires repeated credible signals")
        return {
            "credible_count": credible_count,
            "assessment_counts": dict(sorted(assessment_counts.items())),
        }

    def _require_visible_rumor(self, *, crew_id: str, rumor_id: str) -> dict:
        for rumor in visible_rumors_for_crew(self._event_store, crew_id):
            if rumor.get("rumor_id") == rumor_id:
                return rumor
        raise KeyError(rumor_id)

    def _append_rumor_response_outcome(
        self,
        *,
        player_id: str,
        crew_id: str,
        action: dict,
        rumor: dict,
        rumor_response_mode: str,
        idempotency_key: str,
    ) -> None:
        if rumor_response_mode == "contain":
            outcome = "containment_started"
            summary = "The crew started counterintelligence to contain a leaked rumor."
            heat_delta = 1
        else:
            outcome = "investigation_started"
            summary = "The crew committed an action to investigate or answer a leaked rumor."
            heat_delta = 0
        payload = {
            "rumor_id": rumor["rumor_id"],
            "action_id": action["action_id"],
            "crew_id": crew_id,
            "source_type": rumor["source_type"],
            "source_id": rumor["source_id"],
            "pressure": rumor["pressure"],
            "mode": rumor_response_mode,
            "outcome": outcome,
            "heat_delta": heat_delta,
            "summary": summary,
        }
        if "leak_vector" in rumor:
            payload["leak_vector"] = rumor["leak_vector"]
        if "contract_id" in rumor:
            payload["contract_id"] = rumor["contract_id"]
        self._event_store.append_command(
            event_type="contract.rumor.responded",
            actor_id=player_id,
            visibility=EventVisibility.crews([crew_id]),
            payload=payload,
            idempotency_key=f"{idempotency_key}:rumor-response",
        )
        if rumor_response_mode == "investigate":
            self._append_rumor_verification_result(
                player_id=player_id,
                crew_id=crew_id,
                action=action,
                rumor=rumor,
                idempotency_key=idempotency_key,
            )

    def _append_rumor_escalation_outcome(
        self,
        *,
        player_id: str,
        crew_id: str,
        action: dict,
        mode: str,
        escalation: dict,
        idempotency_key: str,
    ) -> None:
        payload = {
            "schema_version": 1,
            "action_id": action["action_id"],
            "crew_id": crew_id,
            "mode": mode,
            "credible_count": int(escalation["credible_count"]),
            "assessment_counts": dict(escalation["assessment_counts"]),
            "summary": self._rumor_escalation_summary(mode),
        }
        self._event_store.append_command(
            event_type="contract.rumor.escalated",
            actor_id=player_id,
            visibility=EventVisibility.crews([crew_id]),
            payload=payload,
            idempotency_key=f"{idempotency_key}:rumor-escalation",
        )

    def _append_rumor_verification_result(
        self,
        *,
        player_id: str,
        crew_id: str,
        action: dict,
        rumor: dict,
        idempotency_key: str,
    ) -> None:
        assessment, summary = self._rumor_verification_assessment(rumor)
        payload = {
            "schema_version": 1,
            "rumor_id": rumor["rumor_id"],
            "action_id": action["action_id"],
            "crew_id": crew_id,
            "source_type": rumor["source_type"],
            "source_id": rumor["source_id"],
            "pressure": rumor["pressure"],
            "assessment": assessment,
            "confidence": "medium",
            "summary": summary,
        }
        if "leak_vector" in rumor:
            payload["leak_vector"] = rumor["leak_vector"]
        if "contract_id" in rumor:
            payload["contract_id"] = rumor["contract_id"]
        self._event_store.append_command(
            event_type="contract.rumor.verified",
            actor_id=player_id,
            visibility=EventVisibility.crews([crew_id]),
            payload=payload,
            idempotency_key=f"{idempotency_key}:rumor-verification",
        )

    def _rumor_verification_assessment(self, rumor: dict) -> tuple[str, str]:
        pressure = rumor.get("pressure")
        leak_vector = rumor.get("leak_vector")
        if (
            pressure == "artifact_reference_detected"
            and leak_vector == "artifact_name_mention"
        ):
            return (
                "credible_artifact_mention_signal",
                (
                    "The investigation found a credible artifact-name signal, "
                    "but not enough to expose the private source."
                ),
            )
        if pressure == "escrow_terms_detected" and leak_vector == "soft_term_reference":
            return (
                "credible_soft_term_signal",
                (
                    "The investigation found a credible soft-term signal, but "
                    "not enough to expose the private source."
                ),
            )
        if pressure == "artifact_reference_detected":
            return (
                "credible_artifact_signal",
                (
                    "The investigation found a credible artifact signal, but "
                    "not enough to expose the private source."
                ),
            )
        if pressure == "escrow_terms_detected":
            return (
                "credible_arrangement_signal",
                (
                    "The investigation found a credible arrangement signal, but "
                    "not enough to expose the private source."
                ),
            )
        return (
            "inconclusive_signal",
            (
                "The investigation found a rumor signal, but not enough to "
                "expose the private source."
            ),
        )

    def _rumor_escalation_summary(self, mode: str) -> str:
        if mode == "contain":
            return (
                "The crew chose to contain a repeated credible rumor pattern "
                "without exposing private sources."
            )
        if mode == "exploit":
            return (
                "The crew chose to exploit a repeated credible rumor pattern "
                "without exposing private sources."
            )
        return (
            "The crew chose to integrate a repeated credible rumor pattern into "
            "contract strategy without exposing private sources."
        )

    def edit_action(
        self,
        *,
        action_id: str,
        player_id: str,
        intent: str,
        idempotency_key: str,
    ) -> dict:
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "action.edited"
                    or existing.actor_id != player_id
                    or existing.payload["action"]["action_id"] != action_id
                    or existing.payload["action"]["intent"] != intent
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["action"]
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            action = self._current_action(action_id=action_id, player_id=player_id)
            edited = {
                **action,
                "intent": intent,
                "status": "submitted",
            }
            self._event_store.append_command(
                event_type="action.edited",
                actor_id=player_id,
                visibility=EventVisibility.crews([action["crew_id"]]),
                payload={"action": edited},
                idempotency_key=idempotency_key,
            )
            return edited

    def cancel_action(self, *, action_id: str, player_id: str, idempotency_key: str) -> dict:
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "action.canceled"
                    or existing.actor_id != player_id
                    or existing.payload["action"]["action_id"] != action_id
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["action"]
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            action = self._current_action(action_id=action_id, player_id=player_id)
            canceled = {**action, "status": "canceled"}
            self._event_store.append_command(
                event_type="action.canceled",
                actor_id=player_id,
                visibility=EventVisibility.crews([action["crew_id"]]),
                payload={"action": canceled},
                idempotency_key=idempotency_key,
            )
            return canceled

    def current_actions_for_crew(self, crew_id: str) -> list[dict]:
        current: dict[str, dict] = {}
        for event in self._event_store.read_for_principal(Principal.crew(crew_id)):
            if event.type not in {"action.submitted", "action.edited", "action.canceled"}:
                continue
            action = event.payload["action"]
            if action["crew_id"] == crew_id:
                current[action["action_id"]] = action
        return [
            action
            for action in sorted(current.values(), key=lambda item: item["action_id"])
            if action["status"] != "canceled"
        ]

    def _submitted_action_count(self, crew_id: str) -> int:
        return sum(
            1
            for event in self._event_store.read_for_principal(Principal.crew(crew_id))
            if event.type == "action.submitted"
        )

    def _global_action_count(self) -> int:
        return sum(1 for event in self._event_store.read() if event.type == "action.submitted")

    def _current_action(self, *, action_id: str, player_id: str) -> dict:
        current: dict | None = None
        for crew_id in self._crew_service.crew_ids_for_player(player_id):
            for event in self._event_store.read_for_principal(Principal.crew(crew_id)):
                if event.type not in {"action.submitted", "action.edited", "action.canceled"}:
                    continue
                action = event.payload["action"]
                if action["action_id"] == action_id:
                    current = action
        if current is None:
            raise KeyError(action_id)
        if current["status"] == "canceled":
            raise ValueError("action already canceled")
        return current

    def _event_by_idempotency_key(self, idempotency_key: str):
        for event in self._event_store.read():
            if event.idempotency_key == idempotency_key:
                return event
        return None

    def _award_action_artifacts(
        self,
        *,
        action: dict,
        player_id: str,
        crew_id: str,
    ) -> None:
        if self._artifact_service is None:
            return
        visible = self._artifact_service.visible_artifacts_for_player(
            player_id,
            crew_ids=[crew_id],
        )
        already_visible_artifact_ids = {
            artifact["artifact_id"] for artifact in visible["artifacts"]
        }
        for graph, _ in self._artifact_service.seeded_graphs().values():
            phase = self._contract_phase_name(graph.contract_id)
            candidates = action_unlock_candidates(
                graph=graph,
                contract_id=graph.contract_id,
                phase=phase,
                intent=action["intent"],
                exposed_assets=action.get("exposed_assets", ()),
                already_visible_artifact_ids=already_visible_artifact_ids,
            )
            for candidate in candidates:
                self._artifact_service.grant_artifact_access(
                    artifact_id=candidate.artifact_id,
                    actor_id="server",
                    player_ids=[],
                    crew_ids=[crew_id],
                    reason=candidate.award_reason,
                    idempotency_key=(
                        f"artifact.award.{action['action_id']}.{candidate.artifact_id}"
                    ),
                )

    def _contract_phase_name(self, contract_id: str) -> str:
        if contract_id == STARTER_CONTRACT.contract_id:
            return STARTER_CONTRACT.phase.name
        for event in reversed(self._event_store.read()):
            if (
                event.type == "contract.board.published"
                and event.payload["contract_id"] == contract_id
            ):
                return event.payload["phase"]["name"]
        return "Auction Preview"

    def _auction_preview_locked(self) -> bool:
        return any(
            event.type in {"contract.phase.locked", "contract.phase.resolved"}
            and event.payload["contract_id"] == STARTER_CONTRACT.contract_id
            and event.payload["phase"] == "Auction Preview"
            for event in self._event_store.read()
        )
