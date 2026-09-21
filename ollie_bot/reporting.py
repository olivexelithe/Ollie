from __future__ import annotations

import discord

from ollie_bot.models import StatsComparison


OLLIE_PURPLE = discord.Color.from_str("#8C52FF")


def build_comparison_embed(comparison: StatsComparison) -> discord.Embed:
    missing_names = [difference.name for difference in comparison.differences if difference.kind == "missing_from_stats"]
    embed = discord.Embed(
        title="Ollie Stats Check",
        description="These PvP roster members have not submitted stats yet:",
        color=OLLIE_PURPLE,
    )
    _add_name_list(embed, missing_names)
    embed.set_footer(text="Say 'ollie show me missing stats' or use /statscheck for a fresh check.")
    return embed


def build_clear_embed(comparison: StatsComparison) -> discord.Embed:
    embed = discord.Embed(
        title="Ollie Stats Check",
        description="Everyone on the PvP roster has submitted stats.",
        color=OLLIE_PURPLE,
    )
    return embed


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Ollie Help",
        description="Hi! I show the PvP roster members who have not submitted stats yet.",
        color=OLLIE_PURPLE,
    )
    embed.add_field(
        name="Commands",
        value=(
            "`/statscheck` runs a stats check now.\n"
            "`/scan` does the same thing, in case your fingers remember the old command.\n"
            "`/olliestatus` shows the latest live counts.\n"
            "`/olliehelp` shows this help message."
        ),
        inline=False,
    )
    embed.add_field(
        name="You Can Also Say",
        value=(
            "`ollie show me the list`\n"
            "`ollie show me missing stats`\n"
            "`ollie who hasnt submitted stats`\n"
            "`ollie stats check`"
        ),
        inline=False,
    )
    return embed


def _add_name_list(embed: discord.Embed, names: list[str]) -> None:
    if not names:
        return

    lines: list[str] = []
    for index, name in enumerate(names[:40], start=1):
        lines.append(f"{index}. {name}")

    if len(names) > 40:
        lines.append(f"...and {len(names) - 40} more.")

    embed.add_field(name="Missing Stats", value="\n".join(lines), inline=False)
