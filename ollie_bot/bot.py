from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from ollie_bot.config import Settings, load_settings
from ollie_bot.db import Database
from ollie_bot.models import Issue, RosterEntry
from ollie_bot.reporting import build_buttons_view, build_embed, build_help_embed, build_report, build_status_embed
from ollie_bot.scanner import RosterScanner
from ollie_bot.sheets import RosterSheetClient
from ollie_bot.utils import first_non_empty, names_loosely_match


LOGGER = logging.getLogger("ollie")
FLAG_RE = re.compile(r"\b(OL-[A-F0-9]{6})\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b(\d{1,3})\b")
GROUP_ALIASES = {
    "pvp": {"pvp"},
    "n0va": {"n0va", "nova"},
    "n3": {"n3", "n0va3", "nova3"},
    "guest": {"guest", "guest pass", "guestpass"},
}
ROSTER_TABS = {
    "pvp": "PvP Roster",
    "n0va": "n0va Roster",
    "n3": "n0va3 Roster",
}


class OllieBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.db = Database(settings)
        self.sheet_client = RosterSheetClient(settings)
        self.scanner = RosterScanner(settings)
        self.bg_task: asyncio.Task | None = None

    def _address_for_user(self, user_id: int) -> str:
        if user_id == self.settings.special_daddy_user_id:
            return "daddy"
        return "lovely"

    async def setup_hook(self) -> None:
        await self.db.initialize()
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s", self.user)
        if self.bg_task is None:
            self.bg_task = asyncio.create_task(self._daily_scheduler())

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not await self._is_in_logistics_category(message):
            return

        lowered = message.content.casefold()
        if "show me buttons" in lowered and message.reference and message.reference.message_id:
            target = await message.channel.fetch_message(message.reference.message_id)
            if target.author.id == self.user.id:
                await message.reply("Here you go.", view=build_buttons_view(), mention_author=False)
                return

        if "ollie help" in lowered or lowered.strip() == "help":
            if message.author.id == self.settings.special_daddy_user_id:
                await message.reply("Here you go, daddy.", embed=build_help_embed(), mention_author=False)
            else:
                await message.reply(embed=build_help_embed(), mention_author=False)
            return

        if lowered.strip() in {"status", "ollie status"}:
            status_counts = await self.db.get_issue_status_counts()
            live_issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
            await message.reply(embed=build_status_embed(status_counts, len(live_issues)), mention_author=False)
            return

        if lowered.strip() in {"scan", "ollie scan", "run scan", "run ollie scan", "check roster", "scan roster", "ollie scan roster"}:
            issues = await self.publish_scan_report(force=True)
            if issues:
                await message.reply(
                    f"I've run a fresh scan and posted {len(issues)} issue(s) in Logistic Council for you.",
                    mention_author=False,
                )
            else:
                await message.reply(
                    "I've run a fresh scan and there is nothing new to report right now.",
                    mention_author=False,
                )
            return

        natural_handled = await self._handle_natural_ollie_request(message)
        if natural_handled:
            return

        handled = await self._handle_direct_flag_command(message)
        if handled:
            return

        if message.reference and message.reference.message_id:
            await self._handle_reply_action(message)

    async def _handle_natural_ollie_request(self, message: discord.Message) -> bool:
        lowered = message.content.casefold().strip()
        if not lowered.startswith("ollie"):
            return False

        if lowered in {"ollie", "ollie?"}:
            await message.reply(
                f"I'm here, {self._address_for_user(message.author.id)}. You can ask me to scan, explain a flag, show Vera cases, count roster groups, draft reminders, or tell you what needs review.",
                mention_author=False,
            )
            return True

        if any(phrase in lowered for phrase in ("what can you do", "what do you do", "what can u do")):
            await message.reply(embed=build_help_embed(), mention_author=False)
            return True

        if any(phrase in lowered for phrase in ("vera case", "vera cases", "show vera", "who needs vera")):
            await self._reply_with_vera_cases(message)
            return True

        if any(phrase in lowered for phrase in ("name mismatch", "name mismatches", "wrong names", "name issues", "who needs a name change")):
            await self._reply_with_name_mismatches(message)
            return True

        if any(phrase in lowered for phrase in ("keepshare", "keep share", "shared keep", "shared account")):
            await self._reply_with_keepshare_checks(message)
            return True

        if any(phrase in lowered for phrase in ("compare", "versus", " vs ", "difference", "figures for", "numbers for")):
            handled = await self._handle_comparison_request(message)
            if handled:
                return True

        if any(phrase in lowered for phrase in ("all rosters", "all groups", "full picture", "overview", "summary")):
            await self._reply_with_all_group_overview(message)
            return True

        if any(phrase in lowered for phrase in ("need review", "needs review", "who needs review", "what needs review")):
            await self._reply_with_review_summary(message)
            return True

        if any(phrase in lowered for phrase in ("draft reminders", "draft reminder", "who needs a reminder", "who needs reminders")):
            await self._reply_with_reminder_targets(message)
            return True

        if any(phrase in lowered for phrase in ("remind them", "send reminders", "send reminder", "chase names")):
            await self._reply_with_reminder_targets(message)
            return True

        if any(phrase in lowered for phrase in ("how many", "count", "how much")):
            handled = await self._handle_count_question(message)
            if handled:
                return True

        if any(phrase in lowered for phrase in ("check this", "look at this", "help with this", "can you help", "do this")):
            await message.reply(
                f"I can, {self._address_for_user(message.author.id)}. If you want the quickest route, ask me one of these:\n"
                "- `ollie scan`\n"
                "- `ollie who needs review`\n"
                "- `ollie show vera cases`\n"
                "- `ollie compare pvp to the roster`\n"
                "- `ollie draft reminders`\n"
                "- `ollie explain 3`",
                mention_author=False,
            )
            return True

        if lowered.startswith("ollie do ") or lowered.startswith("ollie can you ") or lowered.startswith("ollie could you "):
            await message.reply(
                f"I can help with that if it fits the roster workflow, {self._address_for_user(message.author.id)}. "
                "Try things like `ollie scan`, `ollie show vera cases`, `ollie who needs review`, `ollie draft reminders`, or `ollie how many people have the n3 tag in Discord vs on the n0va3 roster`.",
                mention_author=False,
            )
            return True

        if lowered.startswith("ollie ") and len(lowered.split()) <= 6:
            await message.reply(
                f"I think you're probably asking for one of my common logistics jobs, {self._address_for_user(message.author.id)}. "
                "Try `ollie scan`, `ollie who needs review`, `ollie compare n0va to the roster`, `ollie show vera cases`, or `ollie explain 2`.",
                mention_author=False,
            )
            return True

        return False

    async def _reply_with_vera_cases(self, message: discord.Message) -> None:
        issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        vera_cases = [issue for issue in issues if issue.kind in {"vera_review_needed", "status_role_conflict"}]
        if not vera_cases:
            await message.reply("I can't see any likely Vera cases in the current live check.", mention_author=False)
            return

        lines = []
        for index, issue in enumerate(vera_cases[:10], start=1):
            who = issue.member_name or issue.roster_name or "Unknown member"
            lines.append(f"{index}. {who}: {issue.summary}")
        if len(vera_cases) > 10:
            lines.append(f"...and {len(vera_cases) - 10} more.")

        await message.reply(
            "These are the current likely Vera cases I can see:\n\n" + "\n".join(lines),
            mention_author=False,
        )

    async def _reply_with_review_summary(self, message: discord.Message) -> None:
        issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        if not issues:
            await message.reply("Nothing needs review right now from the live check.", mention_author=False)
            return

        nickname_count = sum(1 for issue in issues if issue.kind == "nickname_mismatch")
        vera_count = sum(1 for issue in issues if issue.kind in {"vera_review_needed", "status_role_conflict"})
        keepshare_count = sum(1 for issue in issues if issue.kind == "keepshare_name_missing")
        guest_count = sum(1 for issue in issues if issue.kind == "guest_pass_review")
        roster_count = sum(1 for issue in issues if issue.kind == "roster_unmatched")

        await message.reply(
            "From the current live check, this is what still needs eyes on:\n"
            f"- Name mismatches: {nickname_count}\n"
            f"- Possible Vera cases: {vera_count}\n"
            f"- Keepshare checks: {keepshare_count}\n"
            f"- Guest pass reviews: {guest_count}\n"
            f"- Roster names not matched: {roster_count}",
            mention_author=False,
        )

    async def _reply_with_name_mismatches(self, message: discord.Message) -> None:
        issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        mismatches = [issue for issue in issues if issue.kind == "nickname_mismatch"]
        if not mismatches:
            await message.reply("I can't see any current name mismatches right now.", mention_author=False)
            return
        lines = []
        for issue in mismatches[:10]:
            who = issue.member_name or "Unknown member"
            roster_name = issue.roster_name or "unknown roster name"
            label = issue.report_number or "?"
            lines.append(f"{label}. {who} should likely match `{roster_name}`.")
        if len(mismatches) > 10:
            lines.append(f"...and {len(mismatches) - 10} more.")
        await message.reply("These are the current name mismatches I can see:\n\n" + "\n".join(lines), mention_author=False)

    async def _reply_with_keepshare_checks(self, message: discord.Message) -> None:
        issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        keepshare_issues = [issue for issue in issues if issue.kind == "keepshare_name_missing"]
        if not keepshare_issues:
            await message.reply("I can't see any keepshare name problems right now.", mention_author=False)
            return
        lines = []
        for issue in keepshare_issues[:10]:
            who = issue.member_name or "Unknown member"
            label = issue.report_number or "?"
            lines.append(f"{label}. {who}: keep name is missing from the server name.")
        if len(keepshare_issues) > 10:
            lines.append(f"...and {len(keepshare_issues) - 10} more.")
        await message.reply("These are the keepshare checks that still look open:\n\n" + "\n".join(lines), mention_author=False)

    async def _reply_with_all_group_overview(self, message: discord.Message) -> None:
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            await message.reply("I couldn't reach the server for that check, lovely.", mention_author=False)
            return

        roster = await self.sheet_client.fetch_roster()
        lines = ["Here is the current roster picture I can see:"]
        for group_key in ("pvp", "n0va", "n3"):
            result = self._compare_group(guild, roster, group_key)
            if result is None:
                continue
            lines.append(
                f"- {group_key.upper()}: roster {result['roster_count']}, Discord role {result['role_count']}, "
                f"matched {result['matched_count']}, roster missing in role {result['missing_count']}, extras in role {result['extra_count']}"
            )

        guest_role = self._resolve_group_role(guild, "guest")
        if guest_role is not None:
            guest_count = sum(1 for member in guild.members if not member.bot and guest_role in member.roles)
            lines.append(f"- Guest pass: {guest_count} member(s) currently hold the guest pass role.")

        await message.reply("\n".join(lines), mention_author=False)

    async def _reply_with_reminder_targets(self, message: discord.Message) -> None:
        issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        reminder_targets = [issue for issue in issues if issue.kind == "nickname_mismatch" and issue.member_name]
        if not reminder_targets:
            await message.reply("I can't see any obvious reminder targets right now.", mention_author=False)
            return

        lines = []
        for index, issue in enumerate(reminder_targets[:10], start=1):
            lines.append(f"{index}. {issue.member_name} should probably get a name update reminder.")
        if len(reminder_targets) > 10:
            lines.append(f"...and {len(reminder_targets) - 10} more.")

        await message.reply(
            "These are the members who currently look like reminder candidates:\n\n" + "\n".join(lines),
            mention_author=False,
        )

    async def _handle_count_question(self, message: discord.Message) -> bool:
        lowered = message.content.casefold()
        comparison_handled = await self._handle_comparison_request(message, compact=True)
        if comparison_handled:
            return True
        if any(token in lowered for token in ("n3", "n0va3", "nova3")):
            await self._reply_with_n3_count(message)
            return True
        return False

    async def _reply_with_n3_count(self, message: discord.Message) -> None:
        roster = await self.sheet_client.fetch_roster()
        n3_tab_names = self._candidate_tab_names("n3")
        n3_entries = [entry for entry in roster if entry.worksheet_name.casefold() in n3_tab_names]
        roster_count = len(n3_entries)

        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            await message.reply("I couldn't access the guild to count that, lovely.", mention_author=False)
            return

        n3_role = self._find_role_by_names(guild, {"n3", "n0va3", "nova3"})
        discord_count = 0
        if n3_role is not None:
            discord_count = sum(1 for member in guild.members if not member.bot and any(role.id == n3_role.id for role in member.roles))

        await message.reply(
            f"I can currently see {discord_count} member(s) with the Discord n3-style role and {roster_count} name(s) on the n0va3 roster tab.",
            mention_author=False,
        )

    async def _handle_comparison_request(self, message: discord.Message, compact: bool = False) -> bool:
        lowered = message.content.casefold()
        requested_groups = [group for group, aliases in GROUP_ALIASES.items() if any(alias in lowered for alias in aliases)]
        requested_groups = list(dict.fromkeys(requested_groups))
        if not requested_groups:
            return False

        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            await message.reply("I couldn't reach the server for that comparison, lovely.", mention_author=False)
            return True

        roster = await self.sheet_client.fetch_roster()

        if "guest" in requested_groups and len(requested_groups) == 1:
            guest_role = self._resolve_group_role(guild, "guest")
            if guest_role is None:
                await message.reply("I couldn't find the guest pass role cleanly for that check.", mention_author=False)
                return True
            guest_count = sum(1 for member in guild.members if not member.bot and guest_role in member.roles)
            await message.reply(
                f"I can see {guest_count} member(s) with guest pass right now. Guest pass isn't treated as a daily roster mismatch, but I can still surface it for review when you scan manually or at the monthly sweep.",
                mention_author=False,
            )
            return True

        lines: list[str] = []
        for group in requested_groups:
            if group == "guest":
                continue
            result = self._compare_group(guild, roster, group)
            if result is None:
                continue
            if compact:
                lines.append(
                    f"{group.upper()}: role {result['role_count']}, roster {result['roster_count']}, missing from role {result['missing_count']}, extras in role {result['extra_count']}"
                )
            else:
                lines.append(
                    f"{group.upper()} comparison:\n"
                    f"- Discord role count: {result['role_count']}\n"
                    f"- Roster count: {result['roster_count']}\n"
                    f"- Clean matches: {result['matched_count']}\n"
                    f"- On roster but not in role: {result['missing_count']}\n"
                    f"- In role but not on roster: {result['extra_count']}"
                )
                if result["missing_samples"]:
                    lines.append(f"Missing sample: {', '.join(result['missing_samples'])}")
                if result["extra_samples"]:
                    lines.append(f"Extra sample: {', '.join(result['extra_samples'])}")

        if not lines:
            return False

        await message.reply("\n\n".join(lines), mention_author=False)
        return True

    def _compare_group(self, guild: discord.Guild, roster: list[RosterEntry], group_key: str) -> dict[str, object] | None:
        roster_tab_names = self._candidate_tab_names(group_key)
        role = self._resolve_group_role(guild, group_key)
        if not roster_tab_names or role is None:
            return None

        roster_entries = [entry for entry in roster if entry.worksheet_name.casefold() in roster_tab_names]
        role_members = [member for member in guild.members if not member.bot and role in member.roles]
        missing_entries: list[str] = []

        for entry in roster_entries:
            roster_name = first_non_empty((entry.ign, entry.display_name))
            match = self._find_member_match(role_members, roster_name)
            if match is None:
                missing_entries.append(roster_name)

        extras = []
        roster_names = [first_non_empty((entry.ign, entry.display_name)) for entry in roster_entries]
        for member in role_members:
            member_name = first_non_empty((member.nick, member.display_name, member.name))
            if not any(names_loosely_match(member_name, roster_name) for roster_name in roster_names):
                extras.append(member_name)

        return {
            "group": group_key,
            "role_count": len(role_members),
            "roster_count": len(roster_entries),
            "matched_count": len(roster_entries) - len(missing_entries),
            "missing_count": len(missing_entries),
            "extra_count": len(extras),
            "missing_samples": missing_entries[:5],
            "extra_samples": extras[:5],
        }

    def _find_member_match(self, members: list[discord.Member], roster_name: str) -> discord.Member | None:
        for member in members:
            possible_names = [
                member.nick or "",
                member.display_name or "",
                member.name or "",
                member.global_name or "",
            ]
            if any(names_loosely_match(roster_name, possible_name) for possible_name in possible_names):
                return member
        return None

    def _find_role_by_names(self, guild: discord.Guild, names: set[str]) -> discord.Role | None:
        normalized_names = {name.casefold() for name in names}
        for role in guild.roles:
            if role.name.casefold() in normalized_names:
                return role
        for role in guild.roles:
            lowered = role.name.casefold()
            if any(name in lowered for name in normalized_names):
                return role
        return None

    def _resolve_group_role(self, guild: discord.Guild, group_key: str) -> discord.Role | None:
        if group_key == "pvp":
            return guild.get_role(self.settings.pvp_role_id) or self._find_role_by_names(guild, {"pvp"})
        if group_key == "n0va":
            return guild.get_role(self.settings.n0va_role_id) or self._find_role_by_names(guild, {"n0va", "nova"})
        if group_key == "guest":
            return guild.get_role(self.settings.guest_pass_role_id) or self._find_role_by_names(guild, {"guest pass", "guest"})
        if group_key == "n3":
            return self._find_role_by_names(guild, {"n3", "n0va3", "nova3"})
        return None

    def _candidate_tab_names(self, group_key: str) -> set[str]:
        candidates: set[str] = set()
        configured_names = self.settings.google_worksheet_names

        if group_key == "pvp":
            search_terms = {"pvp"}
        elif group_key == "n0va":
            search_terms = {"n0va", "nova"}
        elif group_key == "n3":
            search_terms = {"n0va3", "nova3", "n3"}
        else:
            search_terms = set()

        default_name = ROSTER_TABS.get(group_key)
        if default_name:
            candidates.add(default_name.casefold())

        for name in configured_names:
            lowered = name.casefold()
            if any(term in lowered for term in search_terms):
                candidates.add(lowered)

        return candidates

    async def _is_in_logistics_category(self, message: discord.Message) -> bool:
        if not isinstance(message.channel, discord.TextChannel):
            return False
        return message.channel.category_id == self.settings.logistics_category_id

    async def _handle_reply_action(self, message: discord.Message) -> None:
        referenced_id = message.reference.message_id
        if referenced_id is None:
            return
        issue_ids = await self.db.find_report_issue_ids(referenced_id)
        if not issue_ids:
            return

        lowered = message.content.casefold()
        if any(token in lowered for token in ("sorted", "done", "reviewed", "handled")):
            await self.db.update_issue_statuses(issue_ids, "reviewed")
            await message.reply(f"Marked this report as reviewed, {self._address_for_user(message.author.id)}.", mention_author=False)
            return

        if "snooze" in lowered or "later" in lowered:
            await self.db.update_issue_statuses(issue_ids, "snoozed")
            await message.reply(f"No problem, {self._address_for_user(message.author.id)}. I've snoozed this report for now.", mention_author=False)
            return

        if "ignore" in lowered:
            await self.db.update_issue_statuses(issue_ids, "ignored")
            await message.reply(f"Okay, {self._address_for_user(message.author.id)}. I'll ignore this one unless it shows up as new later.", mention_author=False)
            return

        if "needs vera" in lowered:
            await message.reply(f"Noted, {self._address_for_user(message.author.id)}. I'll treat this as a Vera follow-up for Logistics.", mention_author=False)
            return

        if "draft dm" in lowered:
            draft = self._member_dm_draft()
            await message.reply(f"Here is the draft I would send, {self._address_for_user(message.author.id)}:\n\n{draft}", mention_author=False)
            return

        if "help" in lowered or "what do i do" in lowered or "how do i use" in lowered:
            if message.author.id == self.settings.special_daddy_user_id:
                await message.reply("Here you go, daddy.", embed=build_help_embed(), mention_author=False)
            else:
                await message.reply(embed=build_help_embed(), mention_author=False)
            return

        if "send it" in lowered:
            sent = await self._attempt_member_outreach(message, issue_ids)
            if sent:
                await message.reply(sent, mention_author=False)
            return

        if "what is this" in lowered or "why is this flagged" in lowered:
            await message.reply(
                f"I flagged this because the roster check found something that does not line up cleanly between the sheet and Discord, {self._address_for_user(message.author.id)}. "
                "If you want, say `help` for the quick guide, `draft dm` for a member message, or `needs vera` if this looks like a Vera case.",
                mention_author=False,
            )
            return

        if "suggested action" in lowered or "what should we do" in lowered:
            await message.reply(
                f"The best next step depends on the issue type, {self._address_for_user(message.author.id)}: name mismatches usually want a reminder, active roles without a roster match usually want Vera review, and keepshare flags usually want a quick name-format check.",
                mention_author=False,
            )
            return

    async def _handle_direct_flag_command(self, message: discord.Message) -> bool:
        lowered = message.content.casefold().strip()
        if not lowered.startswith("ollie "):
            return False

        flag_match = FLAG_RE.search(message.content)
        number_match = NUMBER_RE.search(message.content)
        if not flag_match and not number_match:
            return False

        issue = None
        label = None
        if flag_match:
            label = flag_match.group(1).upper()
            issue = await self._find_issue_by_flag(label)
        elif number_match:
            label = number_match.group(1)
            issue = await self._find_issue_by_number(int(label))

        if issue is None:
            await message.reply(f"I couldn't find `{label}` in the latest scan, {self._address_for_user(message.author.id)}.", mention_author=False)
            return True

        if "ignore" in lowered:
            await self.db.update_issue_statuses([issue.issue_id], "ignored")
            await message.reply(f"Okay, {self._address_for_user(message.author.id)}. I'll ignore `{label}` unless it comes back as something new.", mention_author=False)
            return True

        if "snooze" in lowered:
            await self.db.update_issue_statuses([issue.issue_id], "snoozed")
            await message.reply(f"No problem, {self._address_for_user(message.author.id)}. I've snoozed `{label}` for now.", mention_author=False)
            return True

        if any(token in lowered for token in ("sorted", "done", "reviewed", "handled")):
            await self.db.update_issue_statuses([issue.issue_id], "reviewed")
            await message.reply(f"Marked `{label}` as reviewed, {self._address_for_user(message.author.id)}.", mention_author=False)
            return True

        if "needs vera" in lowered:
            await message.reply(f"Noted, {self._address_for_user(message.author.id)}. `{label}` looks logged as a Vera follow-up.", mention_author=False)
            return True

        if "draft dm" in lowered:
            await message.reply(
                f"Here is the draft I would send for `{label}`, {self._address_for_user(message.author.id)}:\n\n{self._member_dm_draft()}",
                mention_author=False,
            )
            return True

        if "show" in lowered or "explain" in lowered or "why" in lowered:
            await message.reply(
                f"`{label}`: {issue.summary}\nConfidence: {issue.confidence}\nSuggested next step: {issue.recommended_action}",
                mention_author=False,
            )
            return True

        return False

    async def _find_issue_by_flag(self, flag: str) -> Issue | None:
        live_issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        for issue in live_issues:
            if issue.issue_id.upper() == flag.upper():
                return issue
        return None

    async def _find_issue_by_number(self, number: int) -> Issue | None:
        latest_issue_ids = await self.db.latest_report_issue_ids()
        if not latest_issue_ids or number < 1 or number > len(latest_issue_ids):
            return None
        target_issue_id = latest_issue_ids[number - 1]
        live_issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        for issue in live_issues:
            if issue.issue_id == target_issue_id:
                return issue
        return None

    async def _attempt_member_outreach(self, message: discord.Message, issue_ids: list[str]) -> str | None:
        target_issue = await self._find_single_member_issue(issue_ids)
        if target_issue is None:
            return "I need a single member-focused issue for that. If this report covers a few people, reply on the specific one you want me to chase."

        guild = self.get_guild(self.settings.guild_id)
        if guild is None or target_issue.member_id is None:
            return "I couldn't resolve the member for that issue."

        member = guild.get_member(target_issue.member_id)
        if member is None:
            return "I couldn't find that member in the server anymore."

        draft = self._member_dm_draft()
        try:
            await member.send(draft)
            return f"I've sent that reminder to {member.display_name}."
        except discord.Forbidden:
            channel = guild.get_channel(self.settings.name_change_channel_id)
            if isinstance(channel, discord.TextChannel):
                await channel.send(
                    f"{member.mention} your Discord name appears to be out of step with the current roster. "
                    "When you have a moment, please update it so Logistics can keep everything accurate. Thank you."
                )
                return f"{member.display_name} could not be DMed, so I posted in the name change channel instead."
        return "I couldn't send that reminder."

    async def _find_single_member_issue(self, issue_ids: list[str]) -> Issue | None:
        open_issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        candidates = [issue for issue in open_issues if issue.issue_id in issue_ids and issue.member_id is not None]
        return candidates[0] if len(candidates) == 1 else None

    def _member_dm_draft(self) -> str:
        return (
            "Hi lovely, your Discord name looks a little out of step with the current roster. "
            "When you have a moment, could you update it for Logistics please? Thank you."
        )

    async def run_scan(self, persist: bool = True, include_guest_pass_reviews: bool = True) -> list[Issue]:
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            raise RuntimeError("Guild not found. Check GUILD_ID and bot guild access.")
        if not guild.chunked:
            await guild.chunk(cache=True)

        roster = await self.sheet_client.fetch_roster()
        issues = self.scanner.scan(
            guild,
            roster,
            include_guest_pass_reviews=include_guest_pass_reviews,
        )
        if persist:
            await self.db.upsert_issues(issues)
        return issues

    async def publish_scan_report(self, force: bool = False) -> list[Issue]:
        now = datetime.now(ZoneInfo(self.settings.timezone))
        include_guest_pass_reviews = force or now.day == 1
        issues = await self.run_scan(
            persist=True,
            include_guest_pass_reviews=include_guest_pass_reviews,
        )
        channel = self.get_channel(self.settings.logistic_council_channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Logistic council channel not found.")

        if not issues and not force:
            LOGGER.info("No issues found. Staying quiet.")
            return []

        if issues:
            open_issue_ids = await self.db.load_open_issue_ids()
            fresh_issues = [issue for issue in issues if issue.issue_id in open_issue_ids]
            report_issues = fresh_issues or issues
        else:
            report_issues = []

        if not report_issues:
            return []

        report = build_report(report_issues)
        message = await channel.send(embed=build_embed(report))
        report.message_id = message.id
        await self.db.save_report(report)
        try:
            await message.create_thread(name=f"Ollie review {report.report_id}")
        except discord.HTTPException:
            LOGGER.info("Could not create review thread for report %s", report.report_id)
        return report_issues

    async def find_member_issues(self, query: str) -> list[Issue]:
        live_issues = await self.run_scan(persist=False, include_guest_pass_reviews=True)
        lookup = query.casefold().strip()
        matches: list[Issue] = []
        for issue in live_issues:
            haystacks = [
                (issue.member_name or "").casefold(),
                (issue.roster_name or "").casefold(),
                issue.issue_id.casefold(),
            ]
            if any(lookup in haystack for haystack in haystacks if haystack):
                matches.append(issue)
        return matches

    async def _daily_scheduler(self) -> None:
        await self.wait_until_ready()
        tz = ZoneInfo(self.settings.timezone)
        while not self.is_closed():
            now = datetime.now(tz)
            next_run = now.replace(
                hour=self.settings.daily_check_hour,
                minute=self.settings.daily_check_minute,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run = next_run + timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            try:
                await self.publish_scan_report(force=False)
            except Exception:
                LOGGER.exception("Daily scan failed")


def run_bot() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    bot = OllieBot(settings)

    @bot.tree.command(name="scan", description="Run Ollie's roster scan now.", guild=discord.Object(id=settings.guild_id))
    async def scan(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        issues = await bot.publish_scan_report(force=True)
        if issues:
            await interaction.followup.send(f"I've posted the latest scan in Logistics with {len(issues)} issue(s).", ephemeral=True)
        else:
            await interaction.followup.send("Nothing to report right now, so I've stayed quiet in Logistics.", ephemeral=True)

    @bot.tree.command(name="olliescan", description="Run Ollie's roster scan now.", guild=discord.Object(id=settings.guild_id))
    async def olliescan(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        issues = await bot.publish_scan_report(force=True)
        if issues:
            await interaction.followup.send(f"I've posted the latest scan in Logistics with {len(issues)} issue(s).", ephemeral=True)
        else:
            await interaction.followup.send("Nothing to report right now, so I've stayed quiet in Logistics.", ephemeral=True)

    @bot.tree.command(name="olliehelp", description="Show how to use Ollie.", guild=discord.Object(id=settings.guild_id))
    async def olliehelp(interaction: discord.Interaction) -> None:
        if interaction.user.id == settings.special_daddy_user_id:
            await interaction.response.send_message("Here you go, daddy.", embed=build_help_embed())
        else:
            await interaction.response.send_message(embed=build_help_embed())

    @bot.tree.command(name="olliestatus", description="Show Ollie's current queue.", guild=discord.Object(id=settings.guild_id))
    async def olliestatus(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        status_counts = await bot.db.get_issue_status_counts()
        live_issues = await bot.run_scan(persist=False, include_guest_pass_reviews=True)
        await interaction.followup.send(embed=build_status_embed(status_counts, len(live_issues)), ephemeral=True)

    @bot.tree.command(name="member", description="Look up what Ollie knows about one member or name.", guild=discord.Object(id=settings.guild_id))
    @app_commands.describe(query="A Discord name, roster name, or issue ID")
    async def member(interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        matches = await bot.find_member_issues(query)
        if not matches:
            await interaction.followup.send(
                "I couldn't find an active issue for that name right now. They may be clear, named differently, or not part of the latest report.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Ollie Member Lookup: {query}",
            description="Here is what I can currently see from the latest live check.",
            color=discord.Color.from_str("#8C52FF"),
        )
        for issue in matches[:5]:
            who = issue.member_name or issue.roster_name or "Unknown member"
            embed.add_field(
                name=f"{issue.issue_id} · {who}",
                value=(
                    f"{issue.summary}\n"
                    f"Confidence: {issue.confidence}\n"
                    f"Suggested next step: {issue.recommended_action}"
                ),
                inline=False,
            )
        if len(matches) > 5:
            embed.add_field(name="More Matches", value=f"There are {len(matches) - 5} more issue(s) for this search.", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    bot.run(settings.discord_bot_token)
