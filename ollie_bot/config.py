from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "ollie.db"


def _csv_to_ints(value: str) -> tuple[int, ...]:
    if not value.strip():
        return ()
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def _csv_to_strings(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    guild_id: int
    logistics_category_id: int
    logistic_council_channel_id: int
    name_change_channel_id: int
    pvp_role_id: int
    n0va_role_id: int
    guest_pass_role_id: int
    keep_share_role_ids: tuple[int, ...]
    google_sheet_id: str
    google_worksheet_names: tuple[str, ...]
    google_worksheet_range: str
    google_service_account_info: dict
    daily_check_hour: int
    daily_check_minute: int
    timezone: str
    keep_role_prefixes: tuple[str, ...]
    vera_trigger_statuses: tuple[str, ...]
    special_daddy_user_id: int
    db_path: Path = DB_PATH


def load_settings() -> Settings:
    load_dotenv()

    raw_service_account = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"].strip()
    service_account_info = json.loads(raw_service_account)

    return Settings(
        discord_bot_token=os.environ["DISCORD_BOT_TOKEN"],
        guild_id=int(os.environ["GUILD_ID"]),
        logistics_category_id=int(os.environ["LOGISTICS_CATEGORY_ID"]),
        logistic_council_channel_id=int(os.environ["LOGISTIC_COUNCIL_CHANNEL_ID"]),
        name_change_channel_id=int(os.environ["NAME_CHANGE_CHANNEL_ID"]),
        pvp_role_id=int(os.environ["PVP_ROLE_ID"]),
        n0va_role_id=int(os.environ["N0VA_ROLE_ID"]),
        guest_pass_role_id=int(os.environ["GUEST_PASS_ROLE_ID"]),
        keep_share_role_ids=_csv_to_ints(os.getenv("KEEP_SHARE_ROLE_IDS", "")),
        google_sheet_id=os.environ["GOOGLE_SHEET_ID"],
        google_worksheet_names=_csv_to_strings(os.getenv("GOOGLE_WORKSHEET_NAMES", "")),
        google_worksheet_range=os.getenv("GOOGLE_WORKSHEET_RANGE", "B1:F32"),
        google_service_account_info=service_account_info,
        daily_check_hour=int(os.getenv("DAILY_CHECK_HOUR", "9")),
        daily_check_minute=int(os.getenv("DAILY_CHECK_MINUTE", "0")),
        timezone=os.getenv("TIMEZONE", "Europe/London"),
        keep_role_prefixes=_csv_to_strings(os.getenv("KEEP_ROLE_PREFIXES", "keep-,keep share")),
        vera_trigger_statuses=_csv_to_strings(os.getenv("VERA_TRIGGER_STATUSES", "left,guest pass,inactive")),
        special_daddy_user_id=int(os.getenv("SPECIAL_DADDY_USER_ID", "981722363685113907")),
    )
