from __future__ import annotations
import io
import csv
import discord
from discord import app_commands
from discord.ext import commands

from treasury.sheet_handler import SheetHandler
from treasury.utils import require_treasurer_role

class Export(commands.Cog):
    def __init__(self, bot: commands.Bot, config: dict):
        self.bot = bot
        self.config = config
        self.handler = SheetHandler(config)

    @app_commands.command(name="export", description="Export Budget and Reimbursement as CSV.")
    @require_treasurer_role(lambda self: self.config.get("treasurer_role_id"))
    async def export_csv(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Budget
        budget_rows = self.handler.budget_rows()
        reimb_rows = self.handler.reimb_rows()

        files = []
        for name, rows in (("budget.csv", budget_rows), ("reimbursements.csv", reimb_rows)):
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            for r in rows:
                writer.writerow(r)
            csv_bytes = io.BytesIO(csv_buf.getvalue().encode("utf-8"))
            files.append(discord.File(fp=csv_bytes, filename=name))

        await interaction.followup.send(content="Here are the latest CSV exports:", files=files, ephemeral=True)

async def setup(bot: commands.Bot, config: dict):
    cog = Export(bot, config)
    await bot.add_cog(cog)
    return cog
