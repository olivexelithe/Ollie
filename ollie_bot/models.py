from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RosterEntry:
    worksheet_name: str
    row_number: int
    ign: str
    display_name: str = ""
    status: str = ""
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Issue:
    issue_id: str
    kind: str
    severity: str
    confidence: str
    title: str
    summary: str
    member_id: int | None
    member_name: str | None
    roster_name: str | None
    recommended_action: str
    metadata: dict[str, Any] = field(default_factory=dict)
    report_number: int | None = None


@dataclass(slots=True)
class Report:
    report_id: str
    issues: list[Issue]
    message_id: int | None = None


@dataclass(slots=True)
class SavedNote:
    note_id: int
    source_message_id: int
    source_author_id: int
    requested_by_id: int
    channel_id: int
    content: str
    source_author_name: str
    requested_by_name: str
    player_name: str | None
    status: str
    created_at: str
    review_due_at: str | None
    reminder_message_id: int | None = None
