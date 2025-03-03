import json
import discord
from discord.ext import commands, tasks
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse

# ---------------------
# Google Sheets Setup
# ---------------------
with open("config.json") as config_file:
    config = json.load(config_file)

scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gspread_client = gspread.authorize(creds)

spreadsheet = gspread_client.open("Spring 2025 Budget")
worksheet = spreadsheet.get_worksheet(2)  # Accessing the third sheet

# ---------------------
# Discord Bot Setup
# ---------------------
# Track the last processed row number (including header)
last_row_number = 1

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class ReimburseView(discord.ui.View):
    def __init__(self, row_number: int):
        super().__init__(timeout=None)
        self.row_number = row_number

    @discord.ui.button(label="Mark Paid", style=discord.ButtonStyle.success, custom_id="mark_processed")
    async def mark_processed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Update the "Paid" status in column 10 of the given row
            worksheet.update_cell(self.row_number, 10, "yes")
            # Update button style to green (success) and refresh the view
            button.style = discord.ButtonStyle.success
            button.label = "Paid"
            await interaction.response.edit_message(view=self)
        except Exception as e:
            await interaction.response.send_message(f"Failed to update the row: {e}", ephemeral=True)

@tasks.loop(seconds=10.0)
async def poll_sheet():
    global last_row_number
    try:
        data = worksheet.get_all_values()
        if not data or len(data) < 2:  # Only header present, no data rows yet
            return

        # The new row number (last row including header)
        current_row_number = len(data)
        if current_row_number > last_row_number:
            headers = data[0]
            new_row = data[-1]
            current_entry = dict(zip(headers, new_row))
            last_row_number = current_row_number

            channel = bot.get_channel(config['moderator_channel'])
            if channel:
                # Create a minimal embed with only key fields
                embed = discord.Embed(
                    title="New Reimbursement Request",
                    color=discord.Color.green()
                )
                embed.add_field(name="Full Name", value=current_entry.get("Full Name", "N/A"), inline=True)
                embed.add_field(name="Amount ($)", value=current_entry.get("Amount (in $)", "N/A"), inline=True)

                # Process the receipt field if available
                receipt = current_entry.get("Receipt ", "N/A")
                if receipt != "N/A":
                    if "drive.google.com/open" in receipt:
                        try:
                            parsed_url = urllib.parse.urlparse(receipt)
                            query_params = urllib.parse.parse_qs(parsed_url.query)
                            file_id = query_params.get("id", [None])[0]
                            if file_id:
                                direct_link = f"https://drive.google.com/thumbnail?sz=w320&id={file_id}"
                                embed.add_field(name="Receipt", value=receipt, inline=False)
                                embed.set_image(url=direct_link)
                            else:
                                embed.add_field(name="Receipt", value=receipt, inline=False)
                        except Exception as e:
                            embed.add_field(name="Receipt", value=receipt, inline=False)
                    else:
                        embed.add_field(name="Receipt", value=receipt, inline=False)

                view = ReimburseView(current_row_number)
                await channel.send('@everyone', embed=embed, view=view)
            else:
                print("Notification channel not found.")
    except Exception as e:
        print(f"Error while polling sheet: {e}")

@bot.event
async def on_ready():
    print(f"Bot is ready! Logged in as {bot.user.name}")
    poll_sheet.start()

bot.run(config['bot_token'])
