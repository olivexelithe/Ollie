from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ollie_bot.config import Settings, load_settings
from ollie_bot.models import StatsComparison
from ollie_bot.reporting import build_clear_embed, build_comparison_embed, build_help_embed
from ollie_bot.scanner import StatsScanner
from ollie_bot.sheets import SheetClient, SheetSetupError


LOGGER = logging.getLogger("ollie")


class OllieBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.sheet_client = SheetClient(settings)
        self.scanner = StatsScanner()
        self.bg_task: asyncio.Task | None = None
        self.pending_stats_prompts: set[tuple[int, int]] = set()

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        try:
            await self.tree.sync(guild=guild)
        except discord.Forbidden:
            LOGGER.exception(
                "Could not sync slash commands for guild %s. "
                "Ollie will still run, but /statscheck needs the bot to be in that server "
                "with the applications.commands invite scope.",
                self.settings.guild_id,
            )

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s", self.user)
        if self.bg_task is None:
            self.bg_task = asyncio.create_task(self._daily_scheduler())

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        lowered = message.content.casefold().strip()
        pending_key = (message.channel.id, message.author.id)
        if pending_key in self.pending_stats_prompts and lowered in {"yes", "y", "yeah", "yep", "please", "sure"}:
            self.pending_stats_prompts.discard(pending_key)
            try:
                comparison = await self.publish_stats_report(force=True)
                await message.reply(self._summary_reply(comparison), mention_author=False)
            except SheetSetupError as exc:
                await message.reply(
                    f"I can see the spreadsheet, but I need a tiny sheet-name fix: {exc}",
                    mention_author=False,
                )
            return

        if pending_key in self.pending_stats_prompts and lowered in {"no", "n", "nope", "not now"}:
            self.pending_stats_prompts.discard(pending_key)
            await message.reply("No worries, lovely. I will leave the stats list tucked away for now.", mention_author=False)
            return

        if self._looks_like_stats_request(lowered):
            try:
                comparison = await self.publish_stats_report(force=True)
                await message.reply(self._summary_reply(comparison), mention_author=False)
            except SheetSetupError as exc:
                await message.reply(
                    f"I can see the spreadsheet, but I need a tiny sheet-name fix: {exc}",
                    mention_author=False,
                )
            return

        if lowered in {"ollie help", "help"}:
            await message.reply(embed=build_help_embed(), mention_author=False)
            return

        if "ollie" in lowered:
            self.pending_stats_prompts.add(pending_key)
            await message.reply(
                "Do you want to see who hasnt submitted stats?",
                mention_author=False,
            )

    def _looks_like_stats_request(self, lowered: str) -> bool:
        if lowered in {"scan", "statscheck", "stats check"}:
            return True
        if "ollie" not in lowered:
            return False
        request_phrases = (
            "scan",
            "stats",
            "stats check",
            "show me the list",
            "show the list",
            "missing stats",
            "submitted stats",
            "hasnt submitted",
            "hasn't submitted",
            "who is missing",
            "who hasnt",
            "who hasn't",
        )
        return any(phrase in lowered for phrase in request_phrases)

    def _summary_reply(self, comparison: StatsComparison) -> str:
        if comparison.differences:
            return f"I found {len(comparison.differences)} PvP roster member(s) missing from Nova Stats and posted the list."
        return "I checked and everyone on the PvP roster appears to be on Nova Stats. Sparkly clean."

    async def run_stats_check(self) -> StatsComparison:
        roster_names, stats_names = await asyncio.gather(
            self.sheet_client.fetch_roster_names(),
            self.sheet_client.fetch_stats_names(),
        )
        return self.scanner.compare(roster_names, stats_names)

    async def publish_stats_report(self, *, force: bool = False) -> StatsComparison:
        comparison = await self.run_stats_check()
        channel = self.get_channel(self.settings.stats_team_channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Stats team channel not found. Check STATS_TEAM_CHANNEL_ID.")

        if comparison.differences:
            await channel.send(embed=build_comparison_embed(comparison))
        elif force:
            await channel.send(embed=build_clear_embed(comparison))
        else:
            LOGGER.info("No stats differences found. Staying quiet.")

        return comparison

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
                await self.publish_stats_report(force=False)
            except Exception:
                LOGGER.exception("Daily stats check failed")


def run_bot() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    bot = OllieBot(settings)

    async def _run_stats_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            comparison = await bot.publish_stats_report(force=True)
        except SheetSetupError as exc:
            await interaction.followup.send(
                f"I can see the spreadsheet, but I need a tiny sheet-name fix: {exc}",
                ephemeral=True,
            )
            return
        if comparison.differences:
            await interaction.followup.send(
                f"I've posted {len(comparison.differences)} PvP roster member(s) missing from Nova Stats.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send("Everyone on the PvP roster appears to be on Nova Stats.", ephemeral=True)

    @bot.tree.command(name="statscheck", description="Show who is on the PvP roster but missing from Nova Stats.", guild=discord.Object(id=settings.guild_id))
    async def statscheck(interaction: discord.Interaction) -> None:
        await _run_stats_command(interaction)

    @bot.tree.command(name="scan", description="Compare the PvP roster with Nova Stats now.", guild=discord.Object(id=settings.guild_id))
    async def scan(interaction: discord.Interaction) -> None:
        await _run_stats_command(interaction)

    @bot.tree.command(name="olliestatus", description="Show Ollie's latest roster-vs-stats counts.", guild=discord.Object(id=settings.guild_id))
    async def olliestatus(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        comparison = await bot.run_stats_check()
        await interaction.followup.send(embed=build_clear_embed(comparison) if not comparison.differences else build_comparison_embed(comparison), ephemeral=True)

    @bot.tree.command(name="olliehelp", description="Show how to use Ollie.", guild=discord.Object(id=settings.guild_id))
    async def olliehelp(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)

    bot.run(settings.discord_bot_token)
