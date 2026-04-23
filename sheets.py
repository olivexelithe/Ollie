from __future__ import annotations

from collections import defaultdict

import discord

from ollie_bot.config import Settings
from ollie_bot.keepshares import keep_share_keywords, member_keep_share_roles, nickname_mentions_keep
from ollie_bot.models import Issue, RosterEntry
from ollie_bot.utils import first_non_empty, normalize_name, stable_issue_id


class RosterScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def scan(self, guild: discord.Guild, roster: list[RosterEntry]) -> list[Issue]:
        roster_lookup: dict[str, list[RosterEntry]] = defaultdict(list)
        matched_rows: set[tuple[str, int]] = set()
        vera_statuses = {normalize_name(item) for item in self.settings.vera_trigger_statuses}

        for entry in roster:
            for candidate in {normalize_name(entry.ign), normalize_name(entry.display_name)}:
                if candidate:
                    roster_lookup[candidate].append(entry)

        issues: list[Issue] = []
        tracked_role_ids = {
            self.settings.pvp_role_id,
            self.settings.n0va_role_id,
            self.settings.guest_pass_role_id,
        }

        for member in guild.members:
            if member.bot:
                continue
            member_role_ids = {role.id for role in member.roles}
            if not member_role_ids.intersection(tracked_role_ids):
                continue

            keep_roles = member_keep_share_roles(member, self.settings)
            keep_keywords = keep_share_keywords(member, self.settings)
            is_keep_share = bool(keep_roles)
            keep_name_present = nickname_mentions_keep(member, self.settings)

            if is_keep_share and not keep_name_present:
                issues.append(
                    Issue(
                        issue_id=stable_issue_id("keepshare-name", str(member.id)),
                        kind="keepshare_name_missing",
                        severity="medium",
                        title="Keepshare name missing from server name",
                        summary=f"{member.display_name} appears to be a keepshare account, but their server name does not include the keep name.",
                        member_id=member.id,
                        member_name=member.display_name,
                        roster_name=None,
                        recommended_action="Ask the member to add the keep name to their server name.",
                        metadata={"keep_keywords": keep_keywords},
                    )
                )

            if is_keep_share and keep_name_present:
                continue

            matching_entries = self._find_matching_entries(member, roster_lookup, roster)

            unique_matches = self._dedupe_entries(matching_entries)
            matched_entry = unique_matches[0] if len(unique_matches) == 1 else None
            if matched_entry:
                matched_rows.add((matched_entry.worksheet_name, matched_entry.row_number))

            has_active_role = any(role_id in member_role_ids for role_id in (self.settings.pvp_role_id, self.settings.n0va_role_id))
            has_guest_pass = self.settings.guest_pass_role_id in member_role_ids

            if not matched_entry:
                if has_active_role:
                    issues.append(
                        Issue(
                            issue_id=stable_issue_id("vera-review", str(member.id)),
                            kind="vera_review_needed",
                            severity="high",
                            title="Member not on roster but has active role",
                            summary=f"{member.display_name} has a pvp or n0va role but does not appear on the roster.",
                            member_id=member.id,
                            member_name=member.display_name,
                            roster_name=None,
                            recommended_action="This likely needs a Vera check to see whether they should be removed or moved to guest pass.",
                            metadata={"roles": [role.name for role in member.roles if role.id in tracked_role_ids]},
                        )
                    )
                elif has_guest_pass:
                    issues.append(
                        Issue(
                            issue_id=stable_issue_id("guest-missing", str(member.id)),
                            kind="guest_missing_from_roster",
                            severity="medium",
                            title="Guest pass member missing from roster",
                            summary=f"{member.display_name} has guest pass in Discord but does not appear on the roster.",
                            member_id=member.id,
                            member_name=member.display_name,
                            roster_name=None,
                            recommended_action="Check whether this member needs adding to the roster or manual review.",
                        )
                    )
                continue

            roster_name = first_non_empty((matched_entry.ign, matched_entry.display_name))
            nickname = first_non_empty((member.nick, member.display_name))
            if normalize_name(roster_name) not in normalize_name(nickname):
                issues.append(
                    Issue(
                        issue_id=stable_issue_id("nickname-mismatch", str(member.id), roster_name),
                        kind="nickname_mismatch",
                        severity="medium",
                        title="Discord name does not match roster",
                        summary=f"{member.display_name} does not appear to match the roster name {roster_name}.",
                        member_id=member.id,
                        member_name=member.display_name,
                        roster_name=roster_name,
                        recommended_action="Ask Logistics whether Ollie should send a name update reminder.",
                        metadata={"worksheet_name": matched_entry.worksheet_name},
                    )
                )

            status = normalize_name(matched_entry.status)
            if has_active_role and status in vera_statuses:
                issues.append(
                    Issue(
                        issue_id=stable_issue_id("status-role-conflict", str(member.id), status),
                        kind="status_role_conflict",
                        severity="high",
                        title="Roster status conflicts with active role",
                        summary=f"{member.display_name} is marked {matched_entry.status or 'non-active'} on the roster but still has an active role in Discord.",
                        member_id=member.id,
                        member_name=member.display_name,
                        roster_name=roster_name,
                        recommended_action="This may need Vera if the member should be removed or moved to guest pass.",
                        metadata={"roster_status": matched_entry.status},
                    )
                )

        for entry in roster:
            if (entry.worksheet_name, entry.row_number) in matched_rows:
                continue
            roster_name = first_non_empty((entry.ign, entry.display_name))
            issues.append(
                Issue(
                    issue_id=stable_issue_id("roster-unmatched", entry.worksheet_name, roster_name, str(entry.row_number)),
                    kind="roster_unmatched",
                    severity="low",
                    title="Roster entry not matched to Discord",
                    summary=f"{roster_name} appears on the roster tab {entry.worksheet_name} but was not matched to a Discord member with a tracked role.",
                    member_id=None,
                    member_name=None,
                    roster_name=roster_name,
                    recommended_action="Review whether this member has left, changed names, or needs manual matching.",
                    metadata={
                        "row_number": entry.row_number,
                        "worksheet_name": entry.worksheet_name,
                        "column_offset": entry.raw.get("column_offset"),
                    },
                )
            )

        return issues

    def _member_name_candidates(self, member: discord.Member) -> list[str]:
        candidates = [
            normalize_name(member.nick),
            normalize_name(member.display_name),
            normalize_name(member.name),
            normalize_name(member.global_name),
        ]
        return [candidate for candidate in candidates if candidate]

    def _find_matching_entries(
        self,
        member: discord.Member,
        roster_lookup: dict[str, list[RosterEntry]],
        roster: list[RosterEntry],
    ) -> list[RosterEntry]:
        candidates = self._member_name_candidates(member)
        matching_entries: list[RosterEntry] = []

        for candidate in candidates:
            matching_entries.extend(roster_lookup.get(candidate, []))

        if matching_entries:
            return matching_entries

        for entry in roster:
            roster_name = first_non_empty((entry.ign, entry.display_name))
            normalized_roster_name = normalize_name(roster_name)
            if not normalized_roster_name:
                continue
            if any(normalized_roster_name in candidate for candidate in candidates):
                matching_entries.append(entry)

        return matching_entries

    def _dedupe_entries(self, entries: list[RosterEntry]) -> list[RosterEntry]:
        seen: set[int] = set()
        result: list[RosterEntry] = []
        for entry in entries:
            key = (entry.worksheet_name, entry.row_number)
            if key in seen:
                continue
            seen.add(key)
            result.append(entry)
        return result
