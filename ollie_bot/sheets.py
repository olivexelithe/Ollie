from __future__ import annotations

import asyncio

import gspread
from google.oauth2.service_account import Credentials

from ollie_bot.config import Settings
from ollie_bot.models import RosterEntry
from ollie_bot.utils import compact_text


class RosterSheetClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        credentials = Credentials.from_service_account_info(
            settings.google_service_account_info,
            scopes=scopes,
        )
        self.client = gspread.authorize(credentials)

    async def fetch_roster(self) -> list[RosterEntry]:
        return await asyncio.to_thread(self._fetch_roster_sync)

    def _fetch_roster_sync(self) -> list[RosterEntry]:
        sheet = self.client.open_by_key(self.settings.google_sheet_id)
        entries: list[RosterEntry] = []

        if self.settings.google_worksheet_names:
            worksheets = [sheet.worksheet(name) for name in self.settings.google_worksheet_names]
        else:
            worksheets = sheet.worksheets()

        for worksheet in worksheets:
            values = worksheet.get(self.settings.google_worksheet_range)
            for row_index, row in enumerate(values, start=1):
                for col_index, cell in enumerate(row, start=1):
                    ign = compact_text(str(cell))
                    if not ign:
                        continue
                    entries.append(
                        RosterEntry(
                            worksheet_name=worksheet.title,
                            row_number=row_index,
                            ign=ign,
                            raw={"range": self.settings.google_worksheet_range, "column_offset": col_index},
                        )
                    )

        return entries
