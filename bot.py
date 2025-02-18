import json
import discord
from discord.ext import commands, tasks
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse

# ---------------------
# Google Sheets Setup
# ---------------------
config_file = open("config.json")
config = json.load(config_file)
# Define the scope of the application
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

# Authenticate using the service account credentials
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gspread_client = gspread.authorize(creds)

# Open the spreadsheet by name (change "Spring 2025 Budget" if needed)
spreadsheet = gspread_client.open("Spring 2025 Budget")
worksheet = spreadsheet.get_worksheet(2)  # Accessing the third sheet

# ---------------------
# Discord Bot Setup
# ---------------------
last_entry = None

intents = discord.Intents.default()
intents.message_content = True

# Create your bot instance with the intents parameter.
bot = commands.Bot(command_prefix="!", intents=intents)


class ReimburseView(discord.ui.View):
    def __init__(self, row_number: int):
        super().__init__(timeout=None)
        self.row_number = row_number  # Save the row number to update later

    @discord.ui.button(label="Mark Paid", style=discord.ButtonStyle.primary, custom_id="mark_processed")
    async def mark_processed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            worksheet.update_cell(self.row_number, 10, "yes")
            data = worksheet.get_all_values()
            if not data:
                return  # No data in the sheet

            headers = data[0]
            # Get the last row (newest entry)
            last_row = data[-1]
            # Convert the row into a dictionary using headers
            global last_entry
            last_entry = dict(zip(headers, last_row))


            await interaction.response.send_message("REIMBURSEMENT PAID YAYYYY!", ephemeral=False)
        except Exception as e:
            await interaction.response.send_message(f"Failed to update the row: {e}", ephemeral=True)


@tasks.loop(seconds=10.0)
async def poll_sheet():
    global last_entry
    try:
        # Get all the rows from the worksheet
        data = worksheet.get_all_values()
        if not data:
            return  # No data in the sheet

        headers = data[0]
        # Get the last row (newest entry)
        last_row = data[-1]
        # Convert the row into a dictionary using headers
        current_last_entry = dict(zip(headers, last_row))
        # The row number in the sheet (including the header) is:
        row_number = len(data)

        if current_last_entry != last_entry:
            # A change was detected
            last_entry = current_last_entry
            channel = bot.get_channel(config['moderator_channel'])
            await channel.send('@everyone')
            if channel:
                # Create the embed as before
                embed = discord.Embed(
                    title="New Reimbursement Request",
                    description=f"NEW REINBURSEMENT FUCKERS!!!!!!!!!!!",
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
                embed.add_field(
                    name="Links",
                    value="[Venmo](https://venmo.com) | [PayPal](https://paypal.com)",
                    inline=True
                )


                # Process the receipt field.
                receipt = current_last_entry.get("Receipt ", "N/A")
                if "drive.google.com/open" in receipt:
                    try:
                        # Parse the URL to extract the file ID from the query parameter
                        parsed_url = urllib.parse.urlparse(receipt)
                        query_params = urllib.parse.parse_qs(parsed_url.query)
                        file_id = query_params.get("id", [None])[0]
                        if file_id:
                            # Use the direct link format
                            direct_link = f"https://drive.google.com/thumbnail?sz=w320&id={file_id}"
                            embed.add_field(name="Receipt", value=receipt, inline=False)

                            embed.set_image(url=direct_link)
                        else:
                            embed.add_field(name="Receipt", value=receipt, inline=False)
                    except Exception as e:
                        embed.add_field(name="Receipt", value=receipt, inline=False)
                else:
                    embed.add_field(name="Receipt", value=receipt, inline=False)

                view = ReimburseView(row_number)
                await channel.send(embed=embed, view=view)
            else:
                print("Notification channel not found.")
    except Exception as e:
        print(f"Error while polling sheet: {e}")


@bot.event
async def on_ready():
    print(f"Bot is ready! Logged in as {bot.user.name}")
    poll_sheet.start()


bot.run(config['bot_token'])
