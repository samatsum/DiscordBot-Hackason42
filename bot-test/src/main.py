import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from logic.matcher import MatchManager
from logic.api import FTAPIClient

load_dotenv()

class MatchBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        # 共有リソースの保持
        self.matcher = MatchManager()
        self.api = FTAPIClient(os.getenv("FORTYTWO_APP_UID"), os.getenv("FORTYTWO_APP_SECRET"))

    async def setup_hook(self):
        # Cogの動的ロード
        await self.load_extension("cogs.matching_cog")
        
        # 環境変数の安全な読み込み（堅牢性の担保）
        raw_guild_id = os.getenv("GUILD_ID")
        guild = discord.Object(id=int(raw_guild_id)) if raw_guild_id else None
        
        if guild:
            self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

bot = MatchBot()

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))