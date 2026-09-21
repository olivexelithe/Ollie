from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SheetName:
    name: str
    worksheet_name: str
    row_number: int
    column_number: int
    normalized_name: str


@dataclass(slots=True)
class SheetDifference:
    difference_id: str
    kind: str
    name: str
    source_locations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StatsComparison:
    roster_count: int
    stats_count: int
    matched_count: int
    differences: list[SheetDifference]
