"""Player-facing translation of server rejections.

The server signals game-rule rejections through HTTP status codes with short
detail strings ("phase locked", "not a crew member", ...). Raw httpx errors
read as tracebacks to players and agents; this module maps the common
rejections onto plain-language messages with a next step.

`GameCommandError` subclasses `click.ClickException`, so the Typer CLI prints
it as a one-line error, while MCP tool calls surface its message as the tool
error text.
"""

from __future__ import annotations

from typing import Any

import click
import httpx


class GameCommandError(click.ClickException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


_DETAIL_MESSAGES = {
    "phase still active": (
        "The phase is still active, so it cannot be locked yet. Wait for the "
        "phase timer to run down or submit more meaningful actions first."
    ),
    "phase locked": (
        "This phase has already been locked. Actions, dossier edits, and "
        "votes can no longer change this contract; review the reveal instead."
    ),
    "not a crew member": (
        "You are not a member of that crew. Join a crew first, or pass the "
        "crew id of a crew you belong to."
    ),
    "packet lead only": (
        "Only the crew's Packet Lead can update framing or typed claims. Ask "
        "the current lead to make the change, or start a Packet Lead vote."
    ),
    "contract not found": (
        "That contract is not on your board. Check the contract id against "
        "the contract board."
    ),
    "admin token required": (
        "This is an operator-only command and needs HOLLOW_LODGE_ADMIN_TOKEN."
    ),
    "idempotency key conflict": (
        "This command key was already used for a different request. Retry "
        "the command so a fresh key is generated."
    ),
}


def player_message(status_code: int | None, detail: str | None) -> str:
    if detail:
        mapped = _DETAIL_MESSAGES.get(detail)
        if mapped:
            return mapped
        if detail.startswith("unknown citation artifact"):
            artifact_id = detail.split(":", 1)[-1].strip()
            return (
                f"Artifact '{artifact_id}' is not visible to your crew, so it "
                "cannot be cited. Inspect, unlock, or trade for it first."
            )
    if status_code == 401:
        return (
            "The server rejected your credentials. Re-run 'hollow-lodge "
            "onboard' or check the saved token in your config."
        )
    if detail:
        return detail
    return f"The server rejected the request (HTTP {status_code})."


def translate_api_error(exc: Exception) -> GameCommandError | None:
    if isinstance(exc, httpx.HTTPStatusError):
        detail: str | None = None
        try:
            body = exc.response.json()
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = body["detail"]
        except Exception:
            detail = None
        return GameCommandError(
            player_message(exc.response.status_code, detail),
            status_code=exc.response.status_code,
            detail=detail,
        )
    if isinstance(exc, httpx.RequestError):
        return GameCommandError(
            f"Could not reach the server at {exc.request.url.host}. Check "
            "your connection and the configured server URL, then retry."
        )
    return None


class FriendlyApi:
    """Delegating wrapper that converts httpx errors into GameCommandError."""

    def __init__(self, api: Any):
        object.__setattr__(self, "_api", api)

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._api, name)
        if not callable(value):
            return value

        def call(*args: Any, **kwargs: Any) -> Any:
            try:
                return value(*args, **kwargs)
            except Exception as exc:
                translated = translate_api_error(exc)
                if translated is not None:
                    raise translated from exc
                raise

        return call

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._api, name, value)
