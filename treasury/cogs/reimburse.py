import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
import urllib.parse

from treasury.sheet_handler import SheetHandler


# ---------------- Persistent Button View ----------------
class ReimburseView(discord.ui.View):
    def __init__(self, row_number: int, handler: SheetHandler):
        # timeout=None + custom_id makes the view persistent
        super().__init__(timeout=None)
        self.row_number = row_number
        self.handler = handler

    @discord.ui.button(
        label="Mark Paid",
        style=discord.ButtonStyle.danger,
        custom_id="mark_paid_button"
    )
    async def mark_paid(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            ws = self.handler.reimb_ws
            reimb_row = ws.row_values(self.row_number)

            # Column map for Reinbursement:
            #  1 Timestamp | 2 Full Name | 3 Position | 4 Pre-purchase | 5 Method
            #  6 Amount ($)| 7 Venmo/PayPal | 8 Reason | 9 Receipt | 10 Marked Paid
            amount_raw = reimb_row[5] if len(reimb_row) > 5 else "0"
            category = reimb_row[2] if len(reimb_row) > 2 else "Unknown"

            # Mark as paid in Reinbursement tab
            ws.update_cell(self.row_number, 10, "yes")

            # Sync to Budget tab
            try:
                amount = float(str(amount_raw).replace("$", "").replace(",", ""))
            except Exception:
                amount = 0.0
            self.handler.add_to_budget_used(category, amount)

            # Update UI
            button.style = discord.ButtonStyle.success
            button.label = "✅ Paid"
            if interaction.message.embeds:
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.dark_gray()
            else:
                embed = None
            await interaction.response.edit_message(embed=embed, view=self)

            print(f"[INFO] Marked paid row {self.row_number} ({category}) amount ${amount:.2f}")
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error: {e}", ephemeral=True)


# ---------------- Background Watcher ----------------
class ReinbursementWatcher:
    """
    Watches the Reinbursement sheet for new rows and posts embeds
    in the moderator channel with a 'Mark Paid' button.
    """

    def __init__(self, bot: commands.Bot, handler: SheetHandler, config: dict):
        self.bot = bot
        self.handler = handler
        self.config = config
        self.interval = config.get("poll_interval_seconds", 15)

        # Track last processed row (excluding blank/form headers)
        rows = self.handler.reimb_rows()
        self.last_row = len(rows) if rows else 1

        self.poll_reinbursement.change_interval(seconds=self.interval)
        self.poll_reinbursement.start()
        print(f"[INIT] Reinbursement watcher initialized at row {self.last_row}")

    def cog_unload(self):
        self.poll_reinbursement.cancel()

    @tasks.loop(seconds=15.0)
    async def poll_reinbursement(self):
        try:
            # Fetch all valid rows and strip out empties
            rows = self.handler.reimb_rows()
            nonempty = [r for r in rows if any(c.strip() for c in r)]
            current_last = len(nonempty)

            if current_last <= self.last_row:
                return  # nothing new yet

            new_count = current_last - self.last_row
            print(f"[UPDATE] Detected {new_count} new reimbursement row(s).")

            for row_idx in range(self.last_row + 1, current_last + 1):
                new_row = nonempty[row_idx - 1]  # 0-based index in list

                # Skip if already marked paid
                if len(new_row) > 9 and str(new_row[9]).strip().lower() == "yes":
                    print(f"[SKIP] Row {row_idx} already marked paid.")
                    continue

                # Parse key fields safely
                name = new_row[1] if len(new_row) > 1 else "N/A"
                position = new_row[2] if len(new_row) > 2 else "N/A"
                method = new_row[3] if len(new_row) > 3 else "N/A"
                amount = new_row[4] if len(new_row) > 4 else "N/A"
                venmo = new_row[5] if len(new_row) > 5 else "N/A"
                reason = new_row[6] if len(new_row) > 6 else "N/A"
                receipt = new_row[7] if len(new_row) > 7 else "N/A"

                # --- Build embed ---
                embed = discord.Embed(
                    title="💸 New Reimbursement Request",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="Full Name", value=name, inline=True)
                embed.add_field(name="Position", value=position, inline=True)
                embed.add_field(name="Payment Method", value=method, inline=True)
                embed.add_field(name="Amount ($)", value=amount, inline=True)
                embed.add_field(name="Venmo/PayPal", value=venmo, inline=True)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(
                    name="Links",
                    value="[Venmo](https://venmo.com) | [PayPal](https://paypal.com)",
                    inline=True
                )

                # Receipt thumbnail if Google Drive link
                if isinstance(receipt, str) and "drive.google.com" in receipt:
                    parsed = urllib.parse.urlparse(receipt)
                    query = urllib.parse.parse_qs(parsed.query)
                    file_id = query.get("id", [None])[0]
                    if file_id:
                        embed.set_image(url=f"https://drive.google.com/thumbnail?sz=w640&id={file_id}")
                embed.add_field(name="Receipt", value=receipt or "N/A", inline=False)

                # Add interactive view
                view = ReimburseView(row_idx, handler=self.handler)

                channel = self.bot.get_channel(self.config["moderator_channel_id"])
                if channel:
                    await channel.send(content="@everyone", embed=embed, view=view)
                    print(f"[POST] Sent reimbursement row {row_idx} → Discord.")
                else:
                    print("[WARN] Moderator channel not found.")

            self.last_row = current_last  # update pointer
            print(f"[SYNC] Updated last_row → {self.last_row}")

        except Exception as e:
            print(f"[ERROR] Reinbursement poll failed: {e}")

    @poll_reinbursement.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()
        print(f"[READY] Reinbursement watcher active, polling every {self.interval}s.")

# ---------------- Slash Commands ----------------
class Reimburse(commands.Cog):
    def __init__(self, bot: commands.Bot, handler: SheetHandler):
        self.bot = bot
        self.handler = handler

    @app_commands.command(name="reimb_list", description="Show recent reimbursements.")
    @app_commands.describe(count="Number of recent reimbursements to show (default 5)")
    async def reimb_list(self, interaction: discord.Interaction, count: int = 5):
        try:
            rows = self.handler.reimb_rows()
            if not rows or len(rows) <= 1:
                await interaction.response.send_message("⚠️ Reinbursement sheet is empty.", ephemeral=True)
                return

            header = [h.strip().lower() for h in rows[0]]
            paid_col = next((i for i, h in enumerate(header) if "marked paid" in h), None)
            if paid_col is None:
                await interaction.response.send_message("⚠️ 'Marked Paid' column not found.", ephemeral=True)
                return

            recent = rows[-count:]
            embed = discord.Embed(
                title=f"📋 Last {min(count, len(rows)-1)} Reimbursements",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc),
            )

            for row in reversed(recent):
                name = row[1] if len(row) > 1 else "N/A"
                position = row[2] if len(row) > 2 else "N/A"
                amount = row[5] if len(row) > 5 else "N/A"
                paid = row[paid_col] if len(row) > paid_col else "No"
                status = "✅ Paid" if str(paid).strip().lower() == "yes" else "⏳ Pending"
                embed.add_field(
                    name=f"{name} — {position} (${amount})",
                    value=f"Status: {status}",
                    inline=False,
                )

            await interaction.response.send_message(embed=embed, ephemeral=False)

        except Exception as e:
            await interaction.response.send_message(f"⚠️ Failed to load reimbursements: {e}", ephemeral=True)



# ---------------- Cog Entrypoint ----------------
async def setup(bot: commands.Bot, config: dict):
    handler = SheetHandler(config)
    await bot.add_cog(Reimburse(bot, handler))
    # Register the persistent view so old messages keep their buttons alive
    bot.add_view(ReimburseView(0, handler))
    # Start the background watcher
    ReinbursementWatcher(bot, handler, config)
    print("[LOAD] Reinbursement watcher active and slash commands ready.")
