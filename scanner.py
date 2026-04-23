from __future__ import annotations

from collections import Counter

import discord

from ollie_bot.models import Issue, Report
from ollie_bot.utils import stable_issue_id


def build_report(issues: list[Issue]) -> Report:
    report_id = stable_issue_id("report", *(issue.issue_id for issue in issues))
    return Report(report_id=report_id, issues=issues)


def build_embed(report: Report) -> discord.Embed:
    counts = Counter(issue.kind for issue in report.issues)
    embed = discord.Embed(
        title="Ollie Daily Check",
        description="I found a few things worth a look in the roster check.",
        color=discord.Color.from_str("#8C52FF"),
    )
    embed.add_field(
        name="Summary",
        value=(
            f"{len(report.issues)} issue(s)\n"
            f"Nickname mismatches: {counts.get('nickname_mismatch', 0)}\n"
            f"Possible Vera cases: {counts.get('vera_review_needed', 0) + counts.get('status_role_conflict', 0)}\n"
            f"Keepshare checks: {counts.get('keepshare_name_missing', 0)}"
        ),
        inline=False,
    )

    lines: list[str] = []
    for issue in report.issues[:10]:
        lines.append(f"`{issue.issue_id}` {issue.summary}")
    if len(report.issues) > 10:
        lines.append(f"...and {len(report.issues) - 10} more.")

    embed.add_field(name="Details", value="\n".join(lines) or "Nothing to report.", inline=False)
    embed.set_footer(text="Reply in-thread with: sorted, snooze, ignore, needs vera, draft dm, send it, or show me buttons.")
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

