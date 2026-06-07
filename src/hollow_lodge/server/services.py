from __future__ import annotations

import threading

from hollow_lodge.domain.crews import Crew
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.domain.identity import Player, generate_token, hash_token
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.server.auth import authenticate_token


class IdentityService:
    def __init__(self, *, invite_codes: list[str], event_store: JsonlEventStore):
        self._unused_invites = set(invite_codes)
        self._used_invites: set[str] = set()
        self._players: dict[str, Player] = {}
        self._event_store = event_store
        self._lock = threading.RLock()

    def register(self, *, invite_code: str, display_name: str) -> tuple[Player, str]:
        with self._lock:
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
                payload={"player_id": player_id, "display_name": display_name},
                idempotency_key=f"identity.register.{player_id}",
            )
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


class CrewService:
    def __init__(self, *, event_store: JsonlEventStore):
        self._crews: dict[str, Crew] = {}
        self._event_store = event_store
        self._lock = threading.RLock()

    def create_crew(self, *, name: str, owner_id: str) -> Crew:
        with self._lock:
            crew_id = f"crew_{len(self._crews) + 1:04d}"
            crew = Crew(crew_id=crew_id, name=name)
            crew.add_member(owner_id)
            self._crews[crew_id] = crew
            self._event_store.append_command(
                event_type="crew.created",
                actor_id=owner_id,
                visibility=EventVisibility.crews([crew_id]),
                payload={"crew_id": crew_id, "name": name, "owner_id": owner_id},
                idempotency_key=f"crew.create.{crew_id}",
            )
            return crew

    def join_crew(self, *, crew_id: str, player_id: str) -> Crew:
        with self._lock:
            crew = self._crews[crew_id]
            before = len(crew.member_ids)
            crew.add_member(player_id)
            if len(crew.member_ids) != before:
                self._event_store.append_command(
                    event_type="crew.member.joined",
                    actor_id=player_id,
                    visibility=EventVisibility.crews([crew_id]),
                    payload={"crew_id": crew_id, "player_id": player_id},
                    idempotency_key=f"crew.join.{crew_id}.{player_id}",
                )
            return crew
