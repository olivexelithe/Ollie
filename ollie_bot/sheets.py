from __future__ import annotations

import asyncio

import gspread
from gspread import Worksheet
from google.oauth2.service_account import Credentials

from ollie_bot.config import Settings
from ollie_bot.models import SheetName
from ollie_bot.utils import compact_text, normalize_name


class SheetSetupError(RuntimeError):
    pass


def _looks_like_player_name(value: str) -> bool:
    return any(character.isalpha() for character in value)


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

        available_worksheets = spreadsheet.worksheets()
        worksheets = [self._resolve_worksheet(available_worksheets, name) for name in worksheet_names]
        for worksheet in worksheets:
            values = worksheet.get(cell_range)
            for row_index, row in enumerate(values, start=1):
                for column_index, cell in enumerate(row, start=1):
                    name = compact_text(str(cell))
                    normalized_name = normalize_name(name)
                    if not normalized_name or not _looks_like_player_name(name):
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

    def _resolve_worksheet(self, available_worksheets: list[Worksheet], requested_name: str) -> Worksheet:
        requested_norm = normalize_name(requested_name)

        for worksheet in available_worksheets:
            if worksheet.title == requested_name:
                return worksheet

        for worksheet in available_worksheets:
            if normalize_name(worksheet.title) == requested_norm:
                return worksheet

        requested_words = {normalize_name(part) for part in requested_name.split() if normalize_name(part)}
        likely_matches = [
            worksheet
            for worksheet in available_worksheets
            if requested_words and all(word in normalize_name(worksheet.title) for word in requested_words)
        ]
        if len(likely_matches) == 1:
            return likely_matches[0]

        available_names = ", ".join(worksheet.title for worksheet in available_worksheets)
        raise SheetSetupError(
            f"I could not find a worksheet called '{requested_name}'. Available tabs: {available_names}"
        )
