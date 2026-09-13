from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    token: str
    database_path: str
    giveaway_image_url: str | None
    winner_image_url: str | None
    ticket_category_id: int | None
    log_channel_id: int | None
    reward_claim_channel_id: int | None
    default_reward_delay: int
    claim_window_seconds: int
    sync_guild_id: int | None

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is missing from .env")

        def optional_int(name: str) -> int | None:
            value = os.getenv(name, "").strip()
            return int(value) if value.isdigit() else None

        return cls(
            token=token,
            database_path=os.getenv("DATABASE_PATH", "data/giveaway.db"),
            giveaway_image_url=os.getenv("GIVEAWAY_IMAGE_URL", "").strip() or None,
            winner_image_url=os.getenv("WINNER_IMAGE_URL", "").strip() or None,
            ticket_category_id=optional_int("TICKET_CATEGORY_ID"),
            log_channel_id=optional_int("LOG_CHANNEL_ID"),
            reward_claim_channel_id=optional_int("REWARD_CLAIM_CHANNEL_ID"),
            default_reward_delay=_int_env("DEFAULT_REWARD_DELAY", 0),
            claim_window_seconds=max(60, _int_env("CLAIM_WINDOW_SECONDS", 86400)),
            sync_guild_id=optional_int("SYNC_GUILD_ID"),
        )
