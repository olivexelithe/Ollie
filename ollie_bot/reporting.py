from __future__ import annotations

from collections import Counter

import discord

from ollie_bot.models import SheetDifference, StatsComparison


OLLIE_PURPLE = discord.Color.from_str("#8C52FF")


def build_comparison_embed(comparison: StatsComparison) -> discord.Embed:
    counts = Counter(difference.kind for difference in comparison.differences)
    embed = discord.Embed(
        title="Ollie Stats Check",
        description="I checked the PvP roster against Nova Stats and found people who look like they have not submitted stats yet.",
        color=OLLIE_PURPLE,
    )
    embed.add_field(
        name="Summary",
        value=(
            f"Roster names: {comparison.roster_count}\n"
            f"Stats sheet names: {comparison.stats_count}\n"
            f"Matched names: {comparison.matched_count}\n"
            f"Missing from stats: {counts.get('missing_from_stats', 0)}"
        ),
        inline=False,
    )

    missing_from_stats = [item for item in comparison.differences if item.kind == "missing_from_stats"]
    _add_difference_group(embed, "Still Need Stats", missing_from_stats)
    embed.set_footer(text="Say 'ollie show me missing stats' or use /statscheck for a fresh check.")
    return embed


def build_clear_embed(comparison: StatsComparison) -> discord.Embed:
    embed = discord.Embed(
        title="Ollie Stats Check",
        description="Everyone on the PvP roster appears to be on Nova Stats. Lovely tidy work.",
        color=OLLIE_PURPLE,
    )
    embed.add_field(
        name="Summary",
        value=(
            f"Roster names: {comparison.roster_count}\n"
            f"Stats sheet names: {comparison.stats_count}\n"
            f"Matched names: {comparison.matched_count}"
        ),
        inline=False,
    )
    return embed


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Ollie Help",
        description="Hi! I check who is on the PvP roster but missing from Nova Stats.",
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


def _add_difference_group(embed: discord.Embed, title: str, differences: list[SheetDifference]) -> None:
    if not differences:
        return

    lines: list[str] = []
    for difference in differences[:12]:
        locations = "; ".join(difference.source_locations[:2])
        if len(difference.source_locations) > 2:
            locations += f"; +{len(difference.source_locations) - 2} more"
        lines.append(f"`{difference.difference_id}` **{difference.name}**\n{locations}")

    if len(differences) > 12:
        lines.append(f"...and {len(differences) - 12} more.")

    embed.add_field(name=title, value="\n\n".join(lines), inline=False)
