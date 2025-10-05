from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

from treasury.sheet_handler import SheetHandler
from treasury.utils import money

class Summary(commands.Cog):
    def __init__(self, bot: commands.Bot, config: dict):
        self.bot = bot
        self.config = config
        self.handler = SheetHandler(config)

    @app_commands.command(name="summary", description="Show the current treasury summary.")
    async def summary(self, interaction: discord.Interaction):
        bh = self.handler.budget_header_map()
        rows = self.handler.budget_rows()
        if len(rows) < 2:
            await interaction.response.send_message("No budget data found.")
            return

        # Try to compute totals from columns if present
        alloc_col = bh.get("allocated")
        used_col = bh.get("used")
        remaining_col = bh.get("remaining")

        total_alloc = 0.0
        total_used = 0.0
        total_remaining = 0.0

        def to_f(x):
            try:
                return float(str(x).replace("$", "").replace(",", "").strip())
            except:
                return 0.0

        for r in rows[1:]:
            if alloc_col and len(r) >= alloc_col:
                total_alloc += to_f(r[alloc_col - 1])
            if used_col and len(r) >= used_col:
                total_used += to_f(r[used_col - 1])
            if remaining_col and len(r) >= remaining_col:
                total_remaining += to_f(r[remaining_col - 1])

        embed = discord.Embed(title="📊 Treasury Summary", color=discord.Color.blurple())
        embed.add_field(name="Total Allocated", value=money(total_alloc))
        embed.add_field(name="Total Used", value=money(total_used))
        embed.add_field(name="Total Remaining", value=money(total_remaining))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="category", description="Show a single category's budget.")
    @app_commands.describe(name="Exact category/chair (e.g. 'Social Chair')")
    async def category(self, interaction: discord.Interaction, name: str):
        bh = self.handler.budget_header_map()
        rows = self.handler.budget_rows()
        if len(rows) < 2:
            await interaction.response.send_message("No budget data found.")
            return

        cat_col = bh.get("category")
        alloc_col = bh.get("allocated")
        used_col = bh.get("used")
        remaining_col = bh.get("remaining")

        def norm(s): return (s or "").strip().lower()

        target = norm(name)
        for i, r in enumerate(rows[1:], start=2):
            cat = norm(r[cat_col - 1]) if cat_col and len(r) >= cat_col else ""
            if cat == target or cat.startswith(target):
                alloc = r[alloc_col - 1] if alloc_col and len(r) >= alloc_col else "0"
                used = r[used_col - 1] if used_col and len(r) >= used_col else "0"
                rem = r[remaining_col - 1] if remaining_col and len(r) >= remaining_col else "0"

                embed = discord.Embed(title=f"📁 {name}", color=discord.Color.green())
                embed.add_field(name="Allocated", value=money(alloc), inline=True)
                embed.add_field(name="Used", value=money(used), inline=True)
                embed.add_field(name="Remaining", value=money(rem), inline=True)
                await interaction.response.send_message(embed=embed)
                return

        await interaction.response.send_message("❌ Category not found.")

async def setup(bot: commands.Bot, config: dict):
    cog = Summary(bot, config)
    await bot.add_cog(cog)
    return cog
