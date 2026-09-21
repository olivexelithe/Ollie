from __future__ import annotations

import asyncio

import gspread
from google.oauth2.service_account import Credentials

from ollie_bot.config import Settings
from ollie_bot.models import SheetName
from ollie_bot.utils import compact_text, normalize_name


class SheetClient:
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

    async def fetch_roster_names(self) -> list[SheetName]:
        return await asyncio.to_thread(
            self._fetch_names_from_worksheets_sync,
            self.settings.roster_worksheet_names,
            self.settings.roster_range,
        )

    async def fetch_stats_names(self) -> list[SheetName]:
        return await asyncio.to_thread(
            self._fetch_names_from_worksheets_sync,
            (self.settings.stats_worksheet_name,),
            self.settings.stats_range,
        )

    def _fetch_names_from_worksheets_sync(
        self,
        worksheet_names: tuple[str, ...],
        cell_range: str,
    ) -> list[SheetName]:
        spreadsheet = self.client.open_by_key(self.settings.google_sheet_id)
        names: list[SheetName] = []

        worksheets = [spreadsheet.worksheet(name) for name in worksheet_names]
        for worksheet in worksheets:
            values = worksheet.get(cell_range)
            for row_index, row in enumerate(values, start=1):
                for column_index, cell in enumerate(row, start=1):
                    name = compact_text(str(cell))
                    normalized_name = normalize_name(name)
                    if not normalized_name:
                        continue
                    names.append(
                        SheetName(
                            name=name,
                            worksheet_name=worksheet.title,
                            row_number=row_index,
                            column_number=column_index,
                            normalized_name=normalized_name,
                        )
                    )

        return names
