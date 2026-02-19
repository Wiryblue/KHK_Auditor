import discord


class ReimburseView(discord.ui.View):
    def __init__(self, worksheet, row_number: int):
        super().__init__(timeout=None)
        self.worksheet = worksheet
        self.row_number = row_number

    @discord.ui.button(label="Mark Paid", style=discord.ButtonStyle.danger, custom_id="mark_processed")
    async def mark_processed(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.worksheet.update_cell(self.row_number, 10, "Sent")

            button.style = discord.ButtonStyle.success
            button.label = "✅ Paid"

            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = discord.Color.dark_gray()

            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
