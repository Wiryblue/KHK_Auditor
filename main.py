import discord
from discord.ext import commands
import asyncio
import json

from treasury.cogs import reimburse


async def main():
    # Load config
    with open("config.json") as f:
        CONFIG = json.load(f)

    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    # Load the reimbursement cog with config
    await reimburse.setup(bot, CONFIG)

    @bot.event
    async def on_ready():
        print(f"✅ Logged in as {bot.user}")
        try:
            synced = await bot.tree.sync()
            print(f"📘 Synced {len(synced)} slash command(s).")
        except Exception as e:
            print(f"⚠️ Failed to sync commands: {e}")

    await bot.start(CONFIG["bot_token"])


if __name__ == "__main__":
    asyncio.run(main())
