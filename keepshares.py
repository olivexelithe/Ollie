from __future__ import annotations

import json
from collections.abc import Iterable

import aiosqlite

from ollie_bot.config import Settings
from ollie_bot.models import Issue, Report


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.settings.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS issues (
                    issue_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    message_id INTEGER,
                    issue_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def upsert_issues(self, issues: Iterable[Issue]) -> None:
        async with aiosqlite.connect(self.settings.db_path) as db:
            for issue in issues:
                await db.execute(
                    """
                    INSERT INTO issues (issue_id, kind, summary, status, metadata_json)
                    VALUES (?, ?, ?, 'open', ?)
                    ON CONFLICT(issue_id) DO UPDATE SET
                        kind=excluded.kind,
                        summary=excluded.summary,
                        metadata_json=excluded.metadata_json,
                        last_seen_at=CURRENT_TIMESTAMP
                    """,
                    (issue.issue_id, issue.kind, issue.summary, json.dumps(issue.metadata)),
                )
            await db.commit()

    async def load_open_issue_ids(self) -> set[str]:
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute("SELECT issue_id FROM issues WHERE status = 'open'")
            rows = await cursor.fetchall()
        return {row[0] for row in rows}

    async def save_report(self, report: Report) -> None:
        async with aiosqlite.connect(self.settings.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO reports (report_id, message_id, issue_ids_json)
                VALUES (?, ?, ?)
                """,
                (
                    report.report_id,
                    report.message_id,
                    json.dumps([issue.issue_id for issue in report.issues]),
                ),
            )
            await db.commit()

    async def find_report_issue_ids(self, message_id: int) -> list[str]:
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                "SELECT issue_ids_json FROM reports WHERE message_id = ?",
                (message_id,),
            )
            row = await cursor.fetchone()
        if not row:
            return []
        return list(json.loads(row[0]))

    async def update_issue_statuses(self, issue_ids: Iterable[str], status: str) -> None:
        issue_ids = tuple(issue_ids)
        if not issue_ids:
            return
        placeholders = ",".join("?" for _ in issue_ids)
        async with aiosqlite.connect(self.settings.db_path) as db:
            await db.execute(
                f"UPDATE issues SET status = ? WHERE issue_id IN ({placeholders})",
                (status, *issue_ids),
            )
            await db.commit()

