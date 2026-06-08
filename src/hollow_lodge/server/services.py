from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from datetime import UTC, datetime, timedelta

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
from hollow_lodge.server.projections import contract_board_from_events, inbox_from_board
from hollow_lodge.server.seed_data import STARTER_CAMPAIGN, STARTER_CONTRACT, STARTER_HIDDEN_TRUTH
from hollow_lodge.server.auth import authenticate_token
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
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
                    "invite_code": invite_code,
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
                invite_code = event.payload["invite_code"]
                self._unused_invites.discard(invite_code)
                self._used_invites.add(invite_code)
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
                invite = self._invite_by_code(invite_code)
                if invite is not None:
                    self._invites[invite.invite_id] = Invite(
                        invite_id=invite.invite_id,
                        invite_hash=invite.invite_hash,
                        used=True,
                    )
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
        if event.payload["invite_code"] != invite_code or event.payload["display_name"] != display_name:
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
    ):
        self._event_store = event_store
        self._identity_service = identity_service
        self._crew_service = crew_service
        self._lock = threading.RLock()
        self._message_count = 0
        self._rebuild_from_events()

    def send_direct(
        self,
        *,
        sender_player_id: str,
        recipient_player_id: str,
        body: str,
        idempotency_key: str,
    ) -> ChatMessage:
        if not self._identity_service.has_player(recipient_player_id):
            raise KeyError(recipient_player_id)
        with self._lock:
            replay = self._matching_chat_replay(
                idempotency_key=idempotency_key,
                kind="direct",
                sender_player_id=sender_player_id,
                body=body,
                recipient_player_id=recipient_player_id,
            )
            if replay is not None:
                return replay
            message = self._new_message(
                kind="direct",
                sender_player_id=sender_player_id,
                recipient_player_id=recipient_player_id,
                body=body,
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
    ) -> ChatMessage:
        if not self._crew_service.is_member(crew_id=crew_id, player_id=sender_player_id):
            raise PermissionError(crew_id)
        with self._lock:
            replay = self._matching_chat_replay(
                idempotency_key=idempotency_key,
                kind="crew",
                sender_player_id=sender_player_id,
                body=body,
                sender_crew_id=crew_id,
            )
            if replay is not None:
                return replay
            message = self._new_message(
                kind="crew",
                sender_player_id=sender_player_id,
                sender_crew_id=crew_id,
                body=body,
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
    ) -> ChatMessage:
        if not self._crew_service.is_member(crew_id=sender_crew_id, player_id=sender_player_id):
            raise PermissionError(sender_crew_id)
        if not self._crew_service.has_crew(recipient_crew_id):
            raise KeyError(recipient_crew_id)
        with self._lock:
            replay = self._matching_chat_replay(
                idempotency_key=idempotency_key,
                kind="crew_to_crew",
                sender_player_id=sender_player_id,
                body=body,
                sender_crew_id=sender_crew_id,
                recipient_crew_id=recipient_crew_id,
            )
            if replay is not None:
                return replay
            message = self._new_message(
                kind="crew_to_crew",
                sender_player_id=sender_player_id,
                sender_crew_id=sender_crew_id,
                recipient_crew_id=recipient_crew_id,
                body=body,
            )
            self._event_store.append_command(
                event_type="chat.message.created",
                actor_id=sender_player_id,
                visibility=EventVisibility.crews([sender_crew_id, recipient_crew_id]),
                payload=message.__dict__,
                idempotency_key=idempotency_key,
            )
            return message

    def _new_message(self, **kwargs) -> ChatMessage:
        self._message_count += 1
        return ChatMessage(message_id=f"msg_{self._message_count:06d}", **kwargs)

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

    def _rebuild_from_events(self) -> None:
        for event in self._event_store.read():
            if event.type != "chat.message.created":
                continue
            message_id = event.payload["message_id"]
            if message_id.startswith("msg_"):
                self._message_count = max(self._message_count, int(message_id.removeprefix("msg_")))


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
    ):
        self._event_store = event_store
        self._resolution_oracle = (
            resolution_oracle
            if resolution_oracle is not None
            else DeterministicResolutionOracle()
        )
        self._lock = threading.RLock()
        self._seed_starter_contract()

    def board_for_player(self, player_id: str):
        _ = player_id
        return contract_board_from_events(self._event_store.read())

    def inbox_for_player(self, player_id: str):
        return inbox_from_board(player_id=player_id, board=self.board_for_player(player_id))

    def lock_auction_preview(
        self,
        *,
        contract_id: str,
        actor_id: str,
        hours_elapsed: int,
        idempotency_key: str,
    ) -> dict:
        if contract_id != STARTER_CONTRACT.contract_id:
            raise KeyError(contract_id)
        with COMMAND_SERIALIZATION_LOCK, self._lock:
            existing = self._event_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (
                    existing.type != "contract.phase.resolved"
                    or existing.actor_id != actor_id
                    or existing.payload["contract_id"] != contract_id
                    or existing.payload["phase"] != "Auction Preview"
                    or existing.payload["hours_elapsed"] != hours_elapsed
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["reveal"]
            resolved = self._resolved_auction_preview()
            if resolved is not None:
                return resolved
            if hours_elapsed < STARTER_CONTRACT.phase.remaining_hours and self._meaningful_action_count() < 2:
                raise ValueError("phase still active")
            locked = self._locked_auction_preview()
            lock_hours_elapsed = hours_elapsed
            if locked is None:
                self._event_store.append_command(
                    event_type="contract.phase.locked",
                    actor_id="server",
                    visibility=EventVisibility.public(),
                    payload={
                        "contract_id": contract_id,
                        "phase": "Auction Preview",
                        "hours_elapsed": hours_elapsed,
                    },
                    idempotency_key=f"phase-lock.{contract_id}.auction-preview",
                )
            else:
                lock_hours_elapsed = locked["hours_elapsed"]
            reveal = self._build_auction_preview_reveal(contract_id=contract_id)
            self._event_store.append_command(
                event_type="contract.phase.resolved",
                actor_id=actor_id,
                visibility=EventVisibility.public(),
                payload={
                    "contract_id": contract_id,
                    "phase": "Auction Preview",
                    "hours_elapsed": lock_hours_elapsed,
                    "reveal": reveal,
                },
                idempotency_key=idempotency_key,
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

    def _resolved_auction_preview(self) -> dict | None:
        for event in self._event_store.read():
            if (
                event.type in {"contract.phase.locked", "contract.phase.resolved"}
                and event.payload["contract_id"] == STARTER_CONTRACT.contract_id
                and event.payload["phase"] == "Auction Preview"
            ):
                if event.type == "contract.phase.locked":
                    continue
                return event.payload["reveal"]
        return None

    def _locked_auction_preview(self) -> dict | None:
        for event in self._event_store.read():
            if (
                event.type == "contract.phase.locked"
                and event.payload["contract_id"] == STARTER_CONTRACT.contract_id
                and event.payload["phase"] == "Auction Preview"
            ):
                return event.payload
        return None

    def _completed_auction_preview_oracle_audit(self, *, contract_id: str):
        for event in reversed(self._event_store.read()):
            if (
                event.type == "oracle.resolution.completed"
                and event.payload["contract_id"] == contract_id
                and event.payload["phase"] == "Auction Preview"
            ):
                return event
        return None

    def _build_auction_preview_reveal(self, *, contract_id: str) -> dict:
        packet = self._build_auction_preview_packet(contract_id=contract_id)
        input_packet_hash = self._oracle_packet_hash(packet)
        completed_audit = self._completed_auction_preview_oracle_audit(contract_id=contract_id)
        if completed_audit is not None and completed_audit.payload.get("accepted_output") is not None:
            result = validate_auction_preview_result(
                packet=packet,
                result=AuctionPreviewOracleResult.model_validate(
                    completed_audit.payload["accepted_output"],
                ),
            )
            return self._auction_preview_reveal_from_oracle_result(
                contract_id=contract_id,
                result=result,
            )
        self._event_store.append_command(
            event_type="oracle.resolution.requested",
            actor_id="server",
            visibility=EventVisibility.server_only(),
            payload={
                "contract_id": contract_id,
                "phase": "Auction Preview",
                "input_packet_hash": input_packet_hash,
            },
            idempotency_key=f"oracle.resolution.{contract_id}.auction-preview.requested",
        )
        fallback = False
        fallback_reason: str | None = None
        try:
            candidate = self._resolution_oracle.resolve_auction_preview(packet)
            result = validate_auction_preview_result(packet=packet, result=candidate)
        except Exception as exc:
            fallback = True
            fallback_reason = exc.__class__.__name__
            self._event_store.append_command(
                event_type="oracle.resolution.failed",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "contract_id": contract_id,
                    "phase": "Auction Preview",
                    "input_packet_hash": input_packet_hash,
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
                "contract_id": contract_id,
                "phase": "Auction Preview",
                "provider": result.provider.provider,
                "model": result.provider.model,
                "prompt_version": result.provider.prompt_version,
                "fallback": fallback,
                "fallback_reason": fallback_reason,
                "input_packet_hash": input_packet_hash,
                "accepted_output": result.model_dump(mode="json"),
            },
            idempotency_key=f"oracle.resolution.{contract_id}.auction-preview.completed",
        )
        return self._auction_preview_reveal_from_oracle_result(
            contract_id=contract_id,
            result=result,
        )

    def _build_auction_preview_packet(self, *, contract_id: str) -> AuctionPreviewOraclePacket:
        score_inputs = self._auction_preview_score_inputs()
        allowed_evidence_ids = tuple(
            dict.fromkeys(
                (
                    STARTER_FRAGMENT.fragment_id,
                    *(asset.asset_id for asset in STARTER_CONTRACT.evidence_assets),
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
            phase="Auction Preview",
            hidden_truth_summary=STARTER_HIDDEN_TRUTH.summary,
            allowed_reveal_strings=(
                "Auction house provenance is now suspect.",
                "Rival alternate clue paths remain open.",
            ),
            rubric_hooks=STARTER_CONTRACT.proof_dossier_needs,
            crews=tuple(
                AuctionPreviewCrewPacket(
                    crew_id=score_input.crew_id,
                    claim=score_input.claim,
                    reasoning=score_input.reasoning,
                    weaknesses=score_input.weaknesses,
                    provenance_concerns=score_input.provenance_concerns,
                    evidence_ids=tuple(score_input.evidence_ids),
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

    def _auction_preview_reveal_from_oracle_result(
        self,
        *,
        contract_id: str,
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
            "phase": "Auction Preview",
            "status": "resolved",
            "standings": standings,
            "contract_state": list(result.contract_state),
            "narration": result.narration,
        }

    def _oracle_packet_hash(self, packet: AuctionPreviewOraclePacket) -> str:
        return hashlib.sha256(packet.model_dump_json().encode("utf-8")).hexdigest()

    def _auction_preview_score_inputs(self) -> list[AuctionPreviewScoreInput]:
        crew_ids = self._crew_ids()
        actions_by_crew = self._current_actions_by_crew()
        score_inputs: list[AuctionPreviewScoreInput] = []
        for crew_id in crew_ids:
            dossier = self._current_dossier_for_scoring(crew_id)
            submitted_actions = [
                action
                for action in actions_by_crew.get(crew_id, [])
                if action["status"] == "submitted"
            ]
            score_inputs.append(
                AuctionPreviewScoreInput(
                    crew_id=crew_id,
                    claim=dossier.claim,
                    evidence_ids=dossier.evidence_ids,
                    reasoning=dossier.reasoning,
                    weaknesses=dossier.weaknesses,
                    provenance_concerns=dossier.provenance_concerns,
                    exposed_assets=tuple(
                        dict.fromkeys(
                            (
                                *dossier.evidence_ids,
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

    def _meaningful_action_count(self) -> int:
        return sum(
            1
            for actions in self._current_actions_by_crew().values()
            for action in actions
            if action["status"] == "submitted" and self._is_meaningful_auction_preview_action(action)
        )

    def _is_meaningful_auction_preview_action(self, action: dict) -> bool:
        return bool(
            set(action["exposed_assets"])
            & {"fragment_starter_ledger", "asset_door_omen"}
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
    ):
        self._event_store = event_store
        self._identity_service = identity_service
        self._crew_service = crew_service
        self._lock = threading.RLock()
        self._seed_starter_fragment()

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
    def __init__(self, *, event_store: JsonlEventStore, crew_service: CrewService):
        self._event_store = event_store
        self._crew_service = crew_service
        self._lock = threading.RLock()

    def submit_action(
        self,
        *,
        player_id: str,
        crew_id: str,
        intent: str,
        confirmed: bool,
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
                ):
                    raise ValueError("idempotency key conflict")
                return existing.payload["action"]
            if self._auction_preview_locked():
                raise ValueError("phase locked")
            if not confirmed:
                raise ValueError("unconfirmed action was not submitted")
            if not self._crew_service.is_member(crew_id=crew_id, player_id=player_id):
                raise PermissionError(crew_id)
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
            self._event_store.append_command(
                event_type="action.submitted",
                actor_id=player_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={"confirmed": confirmed, "action": action},
                idempotency_key=idempotency_key,
            )
            return action

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

    def _auction_preview_locked(self) -> bool:
        return any(
            event.type in {"contract.phase.locked", "contract.phase.resolved"}
            and event.payload["contract_id"] == STARTER_CONTRACT.contract_id
            and event.payload["phase"] == "Auction Preview"
            for event in self._event_store.read()
        )
