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


@dataclass(slots=True)
class Report:
    report_id: str
    issues: list[Issue]
    message_id: int | None = None
