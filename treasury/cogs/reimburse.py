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
    """Watches the Reinbursement sheet for new entries and posts embeds with a Mark Paid button."""

    def __init__(self, bot: commands.Bot, handler: SheetHandler, config: dict):
        self.bot = bot
        self.handler = handler
        self.config = config
        self.last_row = handler.get_last_nonempty_row_index()
        self.interval = config.get("poll_interval_seconds", 15)
        self.poll_reinbursement.change_interval(seconds=self.interval)
        self.poll_reinbursement.start()

    def cog_unload(self):
        self.poll_reinbursement.cancel()

    @tasks.loop(seconds=15.0)
    async def poll_reinbursement(self):
        try:
            ws = self.handler.reimb_ws
            current_last = self.handler.get_last_nonempty_row_index()
            if current_last <= self.last_row:
                return

            # Only post the truly new rows (can be >1 if multiple were added)
            for row_idx in range(self.last_row + 1, current_last + 1):
                new_row = ws.row_values(row_idx)
                # Skip already-paid lines
                if len(new_row) > 9 and str(new_row[9]).strip().lower() == "yes":
                    continue

                name = new_row[1] if len(new_row) > 1 else "N/A"
                position = new_row[2] if len(new_row) > 2 else "N/A"
                method = new_row[4] if len(new_row) > 4 else "N/A"
                amount = new_row[5] if len(new_row) > 5 else "N/A"
                venmo = new_row[6] if len(new_row) > 6 else "N/A"
                reason = new_row[7] if len(new_row) > 7 else "N/A"
                receipt = new_row[8] if len(new_row) > 8 else "N/A"

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

                # Show Drive image preview if possible
                if isinstance(receipt, str) and "drive.google.com" in receipt:
                    parsed = urllib.parse.urlparse(receipt)
                    query = urllib.parse.parse_qs(parsed.query)
                    file_id = query.get("id", [None])[0]
                    if file_id:
                        embed.set_image(url=f"https://drive.google.com/thumbnail?sz=w640&id={file_id}")
                embed.add_field(name="Receipt", value=receipt or "N/A", inline=False)

                view = ReimburseView(row_idx, handler=self.handler)
                channel = self.bot.get_channel(self.config["moderator_channel_id"])
                if channel:
                    await channel.send(content="@everyone", embed=embed, view=view)
                else:
                    print("[WARN] Moderator channel not found.")

            self.last_row = current_last

        except Exception as e:
            print(f"[ERROR] Reinbursement poll failed: {e}")

    @poll_reinbursement.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()
        print(f"[INIT] Reinbursement watcher started (interval={self.interval}s).")


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

    @app_commands.command(name="budget", description="Show budget by office or overall summary.")
    @app_commands.describe(office="Filter by office name (optional)")
    async def budget(self, interaction: discord.Interaction, office: str = None):
        try:
            rows = self.handler.budget_rows()
            if not rows or len(rows) <= 1:
                await interaction.response.send_message("⚠️ Budget sheet seems empty.", ephemeral=True)
                return

            header = [h.strip().lower() for h in rows[0]]
            office_col = 0  # "Office"
            # "Amount" = allocated total; ensure it's not "used" or "remaining"
            alloc_col = next((i for i, h in enumerate(header) if "amount" in h and "used" not in h and "remain" not in h), 2)
            used_col = next((i for i, h in enumerate(header) if "used" in h), 4)
            remain_col = next((i for i, h in enumerate(header) if "remain" in h), 5)

            def to_float(x):
                try:
                    return float(str(x).replace("$", "").replace(",", "").strip())
                except Exception:
                    return 0.0

            entries = []
            for row in rows[1:]:
                if len(row) <= remain_col:
                    continue
                name = (row[office_col] or "").strip()
                if not name:
                    continue
                allocated = to_float(row[alloc_col])
                used = to_float(row[used_col])
                remaining = to_float(row[remain_col])
                if office and office.lower() not in name.lower():
                    continue
                entries.append((name, allocated, used, remaining))

            if not entries:
                await interaction.response.send_message(
                    f"⚠️ No results for '{office}'." if office else "⚠️ No budget entries found.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"💰 {'Budget for ' + office if office else 'Budget Overview'} (Rows 8–36)",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc),
            )

            total_alloc = total_used = total_remain = 0.0
            for name, alloc, used, remain in entries:
                total_alloc += alloc
                total_used += used
                total_remain += remain
                embed.add_field(
                    name=name,
                    value=f"**Allocated:** ${alloc:,.2f}\n**Used:** ${used:,.2f}\n**Remaining:** ${remain:,.2f}",
                    inline=True,
                )

            if not office:
                embed.add_field(
                    name="**__Totals__**",
                    value=f"**Allocated:** ${total_alloc:,.2f}\n**Used:** ${total_used:,.2f}\n**Remaining:** ${total_remain:,.2f}",
                    inline=False,
                )

            await interaction.response.send_message(embed=embed, ephemeral=False)

        except Exception as e:
            await interaction.response.send_message(f"⚠️ Failed to load budget: {e}", ephemeral=True)


# ---------------- Cog Entrypoint ----------------
async def setup(bot: commands.Bot, config: dict):
    handler = SheetHandler(config)
    await bot.add_cog(Reimburse(bot, handler))
    # Register the persistent view so old messages keep their buttons alive
    bot.add_view(ReimburseView(0, handler))
    # Start the background watcher
    ReinbursementWatcher(bot, handler, config)
    print("[LOAD] Reinbursement watcher active and slash commands ready.")
