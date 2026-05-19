import discord
from bot import config
from tracker.backfill import BackfillEngine, BackfillStatus


class StatsClient(discord.Client):
    def __init__(self, db_path: str, status: BackfillStatus):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents, status=discord.Status.invisible)
        self.db_path = db_path
        self.backfill_status = status
        self.engine = BackfillEngine(db_path, status)

    async def on_ready(self) -> None:
        guild = self.get_guild(config.DISCORD_GUILD_ID)
        if guild is None:
            print(f"[ERROR] Guild {config.DISCORD_GUILD_ID} not found — check DISCORD_GUILD_ID")
            return
        print(f"[ready] Connected to '{guild.name}' ({guild.member_count} members)")
        print("[backfill] Starting...")
        await self.engine.run_all(guild)
        print("[backfill] Complete.")
