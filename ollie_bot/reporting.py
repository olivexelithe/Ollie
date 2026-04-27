from __future__ import annotations

from collections import Counter
from collections import defaultdict

import discord

from ollie_bot.models import Issue, Report
from ollie_bot.utils import stable_issue_id


def build_report(issues: list[Issue]) -> Report:
    for index, issue in enumerate(issues, start=1):
        issue.report_number = index
    report_id = stable_issue_id("report", *(issue.issue_id for issue in issues))
    return Report(report_id=report_id, issues=issues)


def build_embed(report: Report) -> discord.Embed:
    counts = Counter(issue.kind for issue in report.issues)
    embed = discord.Embed(
        title="Ollie Daily Check",
        description="I found a few things worth a look in the roster check. I've grouped them below so the next steps are easier to spot.",
        color=discord.Color.from_str("#8C52FF"),
    )
    embed.add_field(
        name="Summary",
        value=(
            f"{len(report.issues)} issue(s)\n"
            f"Nickname mismatches: {counts.get('nickname_mismatch', 0)}\n"
            f"Possible Vera cases: {counts.get('vera_review_needed', 0) + counts.get('status_role_conflict', 0)}\n"
            f"Keepshare checks: {counts.get('keepshare_name_missing', 0)}\n"
            f"Roster-only names: {counts.get('roster_unmatched', 0)}"
        ),
        inline=False,
    )

    grouped = group_issues(report.issues)
    for heading, issues in grouped:
        lines: list[str] = []
        for issue in issues[:4]:
            lines.append(
                f"`{issue.report_number}.` {issue.summary}\n"
                f"Confidence: {issue.confidence}. Suggested next step: {issue.recommended_action}"
            )
        if len(issues) > 4:
            lines.append(f"...and {len(issues) - 4} more in this group.")
        embed.add_field(name=heading, value="\n\n".join(lines), inline=False)

    embed.set_footer(text="Reply with: sorted, snooze, ignore, needs vera, draft dm, send it, help, or show me buttons.")
    return embed


def build_buttons_view() -> discord.ui.View:
    class OllieActions(discord.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=300)

        @discord.ui.button(label="Mark Reviewed", style=discord.ButtonStyle.success)
        async def mark_reviewed(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.send_message("Reply with `sorted` to mark this report reviewed.", ephemeral=True)

        @discord.ui.button(label="Snooze", style=discord.ButtonStyle.secondary)
        async def snooze(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.send_message("Reply with `snooze` and I will park this for later.", ephemeral=True)

        @discord.ui.button(label="Draft DM", style=discord.ButtonStyle.primary)
        async def draft_dm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.send_message("Reply with `draft dm` and I will prepare the message.", ephemeral=True)

    return OllieActions()


def group_issues(issues: list[Issue]) -> list[tuple[str, list[Issue]]]:
    labels = {
        "vera_review_needed": "Possible Vera Follow-Up",
        "status_role_conflict": "Possible Vera Follow-Up",
        "nickname_mismatch": "Name Mismatches",
        "keepshare_name_missing": "Keepshare Checks",
        "roster_unmatched": "Roster Names Not Matched",
        "guest_pass_review": "Guest Pass Reviews",
    }
    grouped: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        grouped[labels.get(issue.kind, "Other")] .append(issue)

    preferred_order = [
        "Possible Vera Follow-Up",
        "Name Mismatches",
        "Keepshare Checks",
        "Guest Pass Reviews",
        "Roster Names Not Matched",
        "Other",
    ]
    return [(label, grouped[label]) for label in preferred_order if grouped.get(label)]


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Ollie Help",
        description=(
            "I check the roster against Discord, flag anything that looks out of step, "
            "and help Logistics decide what to do next."
        ),
        color=discord.Color.from_str("#8C52FF"),
    )
    embed.add_field(
        name="What I Do",
        value=(
            "- Run a daily roster check\n"
            "- Stay quiet if nothing needs attention\n"
            "- Report issues in Logistic Council\n"
            "- Flag likely Vera cases\n"
            "- Draft or send member reminders when approved\n"
            "- Fall back to the name change channel if DMs are closed\n"
            "- Explain why I flagged something if you ask"
        ),
        inline=False,
    )
    embed.add_field(
        name="Command",
        value="`/scan` or `/olliescan` runs a manual roster check.\n`/olliehelp` shows this guide again.\n`/member` explains one member.\n`/olliestatus` shows my current picture of open work.",
        inline=False,
    )
    embed.add_field(
        name="What To Say In Reply To A Report",
        value=(
            "`sorted` or `done` to mark it handled\n"
            "`snooze` or `later` to park it\n"
            "`ignore` to dismiss it\n"
            "`needs vera` to note Vera follow-up\n"
            "`draft dm` to preview a member message\n"
            "`send it` to send the member reminder\n"
            "`show me buttons` if you want clickable actions\n"
            "`help` if you want Ollie to explain the next step\n"
            "`why is this flagged` if you want the plain-English reason"
        ),
        inline=False,
    )
    embed.add_field(
        name="How I Match Names",
        value=(
            "I look for the roster IGN anywhere in the Discord server name, so the format "
            "does not need to be exact. For keepshares, I also check for the keep name."
        ),
        inline=False,
    )
    embed.add_field(
        name="Easy Examples",
        value=(
            "`ollie scan`\n"
            "`ollie show vera cases`\n"
            "`ollie who needs review`\n"
            "`ollie draft reminders`\n"
            "`ollie compare pvp to the roster`\n"
            "`ollie how many people have the n3 tag in Discord vs on the n0va3 roster`\n"
            "`ollie ignore 4`\n"
            "`ollie explain 7`"
        ),
        inline=False,
    )
    return embed


def build_status_embed(status_counts: dict[str, int], latest_issue_count: int) -> discord.Embed:
    embed = discord.Embed(
        title="Ollie Status",
        description="Here is my current picture of the roster queue.",
        color=discord.Color.from_str("#8C52FF"),
    )
    embed.add_field(
        name="Queue",
        value=(
            f"Open: {status_counts.get('open', 0)}\n"
            f"Reviewed: {status_counts.get('reviewed', 0)}\n"
            f"Snoozed: {status_counts.get('snoozed', 0)}\n"
            f"Ignored: {status_counts.get('ignored', 0)}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Latest Scan",
        value=f"{latest_issue_count} issue(s) found in the most recent live check.",
        inline=False,
    )
    return embed
