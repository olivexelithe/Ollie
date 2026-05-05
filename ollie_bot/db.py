from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

import aiosqlite

from ollie_bot.config import Settings
from ollie_bot.models import Issue, Report, SavedNote


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
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_notes (
                    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_message_id INTEGER NOT NULL,
                    source_author_id INTEGER NOT NULL,
                    requested_by_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    source_author_name TEXT NOT NULL,
                    requested_by_name TEXT NOT NULL,
                    player_name TEXT,
                    status TEXT NOT NULL DEFAULT 'temporary',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    review_due_at TEXT,
                    reminder_message_id INTEGER
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

    async def get_issue_status_counts(self) -> dict[str, int]:
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute("SELECT status, COUNT(*) FROM issues GROUP BY status")
            rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

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

    async def latest_report_issue_ids(self) -> list[str]:
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                "SELECT issue_ids_json FROM reports ORDER BY created_at DESC LIMIT 1"
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

    async def create_note(
        self,
        *,
        source_message_id: int,
        source_author_id: int,
        requested_by_id: int,
        channel_id: int,
        content: str,
        source_author_name: str,
        requested_by_name: str,
        player_name: str | None = None,
    ) -> int:
        due_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO saved_notes (
                    source_message_id, source_author_id, requested_by_id, channel_id, content,
                    source_author_name, requested_by_name, player_name, status, review_due_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'temporary', ?)
                """,
                (
                    source_message_id,
                    source_author_id,
                    requested_by_id,
                    channel_id,
                    content,
                    source_author_name,
                    requested_by_name,
                    player_name,
                    due_at,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def find_note_by_source_message(self, source_message_id: int) -> SavedNote | None:
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                """
                SELECT note_id, source_message_id, source_author_id, requested_by_id, channel_id, content,
                       source_author_name, requested_by_name, player_name, status, created_at, review_due_at, reminder_message_id
                FROM saved_notes
                WHERE source_message_id = ?
                ORDER BY note_id DESC
                LIMIT 1
                """,
                (source_message_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_note(row)

    async def get_due_notes(self) -> list[SavedNote]:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                """
                SELECT note_id, source_message_id, source_author_id, requested_by_id, channel_id, content,
                       source_author_name, requested_by_name, player_name, status, created_at, review_due_at, reminder_message_id
                FROM saved_notes
                WHERE status = 'temporary'
                  AND review_due_at IS NOT NULL
                  AND review_due_at <= ?
                  AND reminder_message_id IS NULL
                ORDER BY review_due_at ASC
                """,
                (now,),
            )
            rows = await cursor.fetchall()
        return [note for note in (self._row_to_note(row) for row in rows) if note is not None]

    async def attach_note_reminder(self, note_id: int, reminder_message_id: int) -> None:
        async with aiosqlite.connect(self.settings.db_path) as db:
            await db.execute(
                "UPDATE saved_notes SET reminder_message_id = ? WHERE note_id = ?",
                (reminder_message_id, note_id),
            )
            await db.commit()

    async def find_note_by_reminder_message(self, message_id: int) -> SavedNote | None:
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                """
                SELECT note_id, source_message_id, source_author_id, requested_by_id, channel_id, content,
                       source_author_name, requested_by_name, player_name, status, created_at, review_due_at, reminder_message_id
                FROM saved_notes
                WHERE reminder_message_id = ?
                LIMIT 1
                """,
                (message_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_note(row)

    async def update_note_status(self, note_id: int, status: str, player_name: str | None = None) -> None:
        async with aiosqlite.connect(self.settings.db_path) as db:
            await db.execute(
                """
                UPDATE saved_notes
                SET status = ?, player_name = COALESCE(?, player_name)
                WHERE note_id = ?
                """,
                (status, player_name, note_id),
            )
            await db.commit()

    async def search_notes(self, query: str) -> list[SavedNote]:
        like_query = f"%{query.lower()}%"
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                """
                SELECT note_id, source_message_id, source_author_id, requested_by_id, channel_id, content,
                       source_author_name, requested_by_name, player_name, status, created_at, review_due_at, reminder_message_id
                FROM saved_notes
                WHERE lower(content) LIKE ?
                   OR lower(source_author_name) LIKE ?
                   OR lower(requested_by_name) LIKE ?
                   OR lower(COALESCE(player_name, '')) LIKE ?
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (like_query, like_query, like_query, like_query),
            )
            rows = await cursor.fetchall()
        return [note for note in (self._row_to_note(row) for row in rows) if note is not None]

    async def recent_notes(self, days: int = 7) -> list[SavedNote]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self.settings.db_path) as db:
            cursor = await db.execute(
                """
                SELECT note_id, source_message_id, source_author_id, requested_by_id, channel_id, content,
                       source_author_name, requested_by_name, player_name, status, created_at, review_due_at, reminder_message_id
                FROM saved_notes
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (cutoff,),
            )
            rows = await cursor.fetchall()
        return [note for note in (self._row_to_note(row) for row in rows) if note is not None]

    def _row_to_note(self, row: tuple | None) -> SavedNote | None:
        if row is None:
            return None
        return SavedNote(
            note_id=row[0],
            source_message_id=row[1],
            source_author_id=row[2],
            requested_by_id=row[3],
            channel_id=row[4],
            content=row[5],
            source_author_name=row[6],
            requested_by_name=row[7],
            player_name=row[8],
            status=row[9],
            created_at=row[10],
            review_due_at=row[11],
            reminder_message_id=row[12],
        )
