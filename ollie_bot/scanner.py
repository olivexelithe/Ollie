from __future__ import annotations

from collections import defaultdict

from ollie_bot.models import SheetDifference, SheetName, StatsComparison
from ollie_bot.utils import stable_issue_id


class StatsScanner:
    def compare(self, roster_names: list[SheetName], stats_names: list[SheetName]) -> StatsComparison:
        roster_lookup = self._group_by_normalized_name(roster_names)
        stats_lookup = self._group_by_normalized_name(stats_names)

        roster_keys = set(roster_lookup)
        stats_keys = set(stats_lookup)
        matched_keys = roster_keys.intersection(stats_keys)
        differences: list[SheetDifference] = []

        for key in sorted(roster_keys - stats_keys):
            entries = roster_lookup[key]
            display_name = self._best_display_name(entries)
            differences.append(
                SheetDifference(
                    difference_id=stable_issue_id("missing-from-stats", key),
                    kind="missing_from_stats",
                    name=display_name,
                    source_locations=self._locations(entries),
                )
            )

        return StatsComparison(
            roster_count=len(roster_keys),
            stats_count=len(stats_keys),
            matched_count=len(matched_keys),
            differences=differences,
        )

    def _group_by_normalized_name(self, entries: list[SheetName]) -> dict[str, list[SheetName]]:
        grouped: dict[str, list[SheetName]] = defaultdict(list)
        for entry in entries:
            grouped[entry.normalized_name].append(entry)
        return grouped

    def _best_display_name(self, entries: list[SheetName]) -> str:
        return sorted((entry.name for entry in entries), key=lambda value: (len(value), value.casefold()))[0]

    def _locations(self, entries: list[SheetName]) -> list[str]:
        return [
            f"{entry.worksheet_name} row {entry.row_number}, column {entry.column_number}"
            for entry in entries
        ]
