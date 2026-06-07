from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


TOKEN_BYTES = 32


@dataclass(frozen=True)
class Player:
    player_id: str
    display_name: str
    token_hash: str
    token_revoked: bool = False


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(*, provided_token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(provided_token), stored_hash)

