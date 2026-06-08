from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


class ClientConfig(BaseModel):
    server_url: str = Field(min_length=1)
    player_id: str = Field(min_length=1)
    token: str = Field(min_length=1)
    active_crew_id: str | None = None


class OnboardingConfig(BaseModel):
    server_url: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    contact: str | None = None
    request_id: str = Field(min_length=1)
    status: str = Field(min_length=1)


def save_config(path: Path, config: ClientConfig) -> None:
    _save_json(path, config.model_dump_json())


def load_config(path: Path) -> ClientConfig:
    return ClientConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_onboarding_config(path: Path, config: OnboardingConfig) -> None:
    _save_json(path, config.model_dump_json())


def load_onboarding_config(path: Path) -> OnboardingConfig:
    return OnboardingConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _save_json(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.write("\n")
    os.chmod(path, 0o600)
