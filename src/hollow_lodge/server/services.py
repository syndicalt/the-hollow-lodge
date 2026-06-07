from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import UTC, datetime, timedelta

from hollow_lodge.domain.crews import Crew
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.domain.chat import ChatMessage
from hollow_lodge.domain.identity import Player, generate_token, hash_token
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.visibility import Principal
from hollow_lodge.server.projections import contract_board_from_events, inbox_from_board
from hollow_lodge.server.seed_data import STARTER_CAMPAIGN, STARTER_CONTRACT, STARTER_HIDDEN_TRUTH
from hollow_lodge.server.auth import authenticate_token


JOIN_CODE_BYTES = 18
REGISTRATION_REPLAY_TTL = timedelta(minutes=15)


class IdentityService:
    def __init__(self, *, invite_codes: list[str], event_store: JsonlEventStore):
        self._unused_invites = set(invite_codes)
        self._used_invites: set[str] = set()
        self._players: dict[str, Player] = {}
        self._registration_replays: dict[str, tuple[Player, str]] = {}
        self._event_store = event_store
        self._registration_replay_path = event_store.path.with_suffix(".registration-replays.json")
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
            if invite_code not in self._unused_invites:
                raise ValueError("invalid invite")
            player_id = f"player_{len(self._players) + 1:04d}"
            token = generate_token()
            player = Player(
                player_id=player_id,
                display_name=display_name,
                token_hash=hash_token(token),
            )
            self._unused_invites.remove(invite_code)
            self._used_invites.add(invite_code)
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
            elif event.type == "identity.token.revoked":
                player = self._players[event.payload["player_id"]]
                self._players[player.player_id] = Player(
                    player_id=player.player_id,
                    display_name=player.display_name,
                    token_hash=player.token_hash,
                    token_revoked=True,
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
            crew = self._crews[crew_id]
            return player_id in crew.member_ids

    def has_crew(self, crew_id: str) -> bool:
        with self._lock:
            return crew_id in self._crews

    def crew_ids_for_player(self, player_id: str) -> list[str]:
        with self._lock:
            return [
                crew_id
                for crew_id, crew in self._crews.items()
                if player_id in crew.member_ids
            ]

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
    def __init__(self, *, event_store: JsonlEventStore):
        self._event_store = event_store
        self._lock = threading.RLock()
        self._seed_starter_contract()

    def board_for_player(self, player_id: str):
        _ = player_id
        return contract_board_from_events(self._event_store.read())

    def inbox_for_player(self, player_id: str):
        return inbox_from_board(player_id=player_id, board=self.board_for_player(player_id))

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
