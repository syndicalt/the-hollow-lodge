from __future__ import annotations

from typing import Any

from hollow_lodge.client.render_packets import (
    build_contract_board_packet,
    build_inbox_packet,
)


def render_contract_board(board: dict[str, Any]) -> str:
    return build_contract_board_packet(board).player_markdown


def render_inbox(inbox: dict[str, Any]) -> str:
    return build_inbox_packet(inbox).player_markdown
