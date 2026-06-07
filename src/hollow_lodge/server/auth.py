from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hollow_lodge.domain.identity import Player, token_matches


bearer = HTTPBearer(auto_error=False)


def current_player(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Player:
    if credentials is None:
        raise _unauthorized()
    player = request.app.state.identity_service.authenticate(credentials.credentials)
    if player is None:
        raise _unauthorized()
    return player


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate_token(players: dict[str, Player], token: str) -> Player | None:
    for player in players.values():
        if not player.token_revoked and token_matches(
            provided_token=token,
            stored_hash=player.token_hash,
        ):
            return player
    return None

