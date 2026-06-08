from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


TOKEN_BYTES = 32
INVITE_BYTES = 18


@dataclass(frozen=True)
class Player:
    player_id: str
    display_name: str
    token_hash: str
    token_revoked: bool = False


@dataclass(frozen=True)
class AccessKeyRequest:
    request_id: str
    display_name: str
    contact: str | None
    status: str = "pending"


@dataclass(frozen=True)
class Invite:
    invite_id: str
    invite_hash: str
    used: bool = False


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def generate_invite_code() -> str:
    return f"lodge_{secrets.token_urlsafe(INVITE_BYTES)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(*, provided_token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(provided_token), stored_hash)
