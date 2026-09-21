from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _csv_to_strings(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _optional_int(*names: str) -> int | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return int(value)
    return None


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    guild_id: int
    stats_team_channel_id: int
    google_sheet_id: str
    roster_worksheet_names: tuple[str, ...]
    roster_range: str
    stats_worksheet_name: str
    stats_range: str
    google_service_account_info: dict
    daily_check_hour: int
    daily_check_minute: int
    timezone: str


def load_settings() -> Settings:
    load_dotenv()

    raw_service_account = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"].strip()
    service_account_info = json.loads(raw_service_account)
    stats_team_channel_id = _optional_int("STATS_TEAM_CHANNEL_ID") or 1474540598206664794

    return Settings(
        discord_bot_token=os.environ["DISCORD_BOT_TOKEN"],
        guild_id=int(os.environ["GUILD_ID"]),
        stats_team_channel_id=stats_team_channel_id,
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "1EfEbPQcXrQWk_Ybh9n6PfzOse5tRZSoUq5kaPixupjA"),
        roster_worksheet_names=_csv_to_strings(os.getenv("ROSTER_WORKSHEET_NAMES", "PvP Roster")),
        roster_range=os.getenv("ROSTER_RANGE", "B1:F32"),
        stats_worksheet_name=os.getenv("STATS_WORKSHEET_NAME", "Nova Stats"),
        stats_range=os.getenv("STATS_RANGE", "C1:C500"),
        google_service_account_info=service_account_info,
        daily_check_hour=int(os.getenv("DAILY_CHECK_HOUR", "9")),
        daily_check_minute=int(os.getenv("DAILY_CHECK_MINUTE", "0")),
        timezone=os.getenv("TIMEZONE", "Europe/London"),
    )
