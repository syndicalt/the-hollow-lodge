from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


class ClientConfig(BaseModel):
    server_url: str = Field(min_length=1)
    player_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


def save_config(path: Path, config: ClientConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(config.model_dump_json())
        handle.write("\n")
    os.chmod(path, 0o600)


def load_config(path: Path) -> ClientConfig:
    return ClientConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
