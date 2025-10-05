import discord

def require_treasurer_role(role_id: int | None):
    """Decorator to restrict commands to Treasurer role (if configured)."""
    def predicate(interaction: discord.Interaction):
        if role_id is None:
            return True
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            return False
        return any(r.id == role_id for r in interaction.user.roles)
    return discord.app_commands.check(predicate)

def money(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except:
        return str(v or "0")
