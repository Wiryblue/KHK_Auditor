import json
import discord
from discord.ext import commands, tasks
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse
from gspread.utils import rowcol_to_a1

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
worksheet = spreadsheet.get_worksheet(3)  # Accessing the third sheet

# ---------------------
# Discord Bot Setup
# ---------------------
# Tracks the last processed non-empty row (including header)
last_row_number = 1

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


class ReimburseView(discord.ui.View):
    def __init__(self, row_number: int):
        super().__init__(timeout=None)
        self.row_number = row_number

    @discord.ui.button(label="Click to Mark Paid", style=discord.ButtonStyle.danger, custom_id="mark_processed")
    async def mark_processed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Update the "Paid" status in column 10 for the given row
            worksheet.update_cell(self.row_number, 10, "yes")
            # Change button style and label to indicate payment has been made
            button.style = discord.ButtonStyle.success
            button.label = "Paid"

            # Retrieve the original embed from the message and update its color to simulate lower opacity
            if interaction.message.embeds:
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.dark_gray()
            else:
                embed = None

            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            await interaction.response.send_message(f"Failed to update the row: {e}", ephemeral=True)


@tasks.loop(seconds=10.0)
async def poll_sheet():
    global last_row_number
    try:
        # Define the range to capture all cells
        range_end = rowcol_to_a1(worksheet.row_count, worksheet.col_count)
        data = worksheet.get_values(f"A1:{range_end}")
        if not data:
            return

        # Filter out completely empty rows
        non_empty_rows = [row for row in data if any(cell.strip() for cell in row)]
        if len(non_empty_rows) < 2:  # Only header exists or no valid data
            return

        current_row_number = len(non_empty_rows)
        if current_row_number > last_row_number:
            headers = non_empty_rows[0]
            new_row = non_empty_rows[-1]
            current_last_entry = dict(zip(headers, new_row))
            last_row_number = current_row_number

            channel = bot.get_channel(config['moderator_channel'])
            if channel:
                embed = discord.Embed(
                    title="New Reimbursement Request",
                    color=discord.Color.green()
                )
                embed.add_field(name="Full Name", value=current_last_entry.get("Full Name", "N/A"), inline=True)
                embed.add_field(name="Position", value=current_last_entry.get("Position", "N/A"), inline=True)
                embed.add_field(name="Pre-purchase Form", value=current_last_entry.get("Pre-purchase Form", "N/A"),
                                inline=False)
                embed.add_field(name="Amount (in $)", value=current_last_entry.get("Amount (in $)", "N/A"), inline=True)
                embed.add_field(name="Venmo/Paypal Details",
                                value=current_last_entry.get("Venmo/paypal details", "N/A"), inline=True)
                embed.add_field(name="Reason for Expenditure",
                                value=current_last_entry.get("Reason for expenditure", "N/A"), inline=False)
                embed.add_field(name="Payment Method", value=current_last_entry.get("Self paid or KHK card?", "N/A"),
                                inline=True)
                embed.add_field(name="Links", value="[Venmo](https://venmo.com) | [PayPal](https://paypal.com)",
                                inline=True)

                # Receipt handling
                receipt = current_last_entry.get("Receipt ", "N/A")
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
    global last_row_number
    print(f"Bot is ready! Logged in as {bot.user.name}")
    # Initialize last_row_number to ignore old entries at startup
    range_end = rowcol_to_a1(worksheet.row_count, worksheet.col_count)
    data = worksheet.get_values(f"A1:{range_end}")
    non_empty_rows = [row for row in data if any(cell.strip() for cell in row)]
    last_row_number = len(non_empty_rows) if non_empty_rows else 1
    poll_sheet.start()


bot.run(config['bot_token'])
