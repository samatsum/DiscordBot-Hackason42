import os
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
from datetime import datetime, timedelta, time as dt_time

from logic.models import MealRequest
from logic.matcher import MatchManager
from logic.api import FTAPIClient

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") #
GUILD_ID = os.getenv("GUILD_ID") #[cite: 3]
UID = os.getenv("FORTYTWO_APP_UID") #[cite: 3]
SECRET = os.getenv("FORTYTWO_APP_SECRET") #[cite: 3]

class MealBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all()) # メンバー取得のためAll推奨
        self.tree = app_commands.CommandTree(self)
        self.matcher = MatchManager()
        self.api = FTAPIClient(UID, SECRET)

    async def setup_hook(self):
        self.cleanup_task.start()
        guild = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None
        if guild: self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    @tasks.loop(time=[dt_time(hour=h, minute=m) for h in range(24) for m in [0, 15, 30, 45]])
    async def cleanup_task(self):
        self.matcher.cleanup(datetime.now())

client = MealBot()

# --- オートコンプリート ---

async def time_autocomplete(it: discord.Interaction, current: str):
    now = datetime.now()
    base = now.replace(second=0, microsecond=0)
    if base.minute % 15 != 0: base += timedelta(minutes=(15 - base.minute % 15))
    times = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(25)]
    return [app_commands.Choice(name=t, value=t) for t in times if current in t]

async def intra_autocomplete(it: discord.Interaction, current: str):
    """サーバーのメンバーからIntra名の候補を提示"""
    members = it.guild.members if it.guild else []
    # 表示名やニックネームから前方一致で検索（42のDiscord運用を想定）
    choices = [m.display_name for m in members if current.lower() in m.display_name.lower()]
    return [app_commands.Choice(name=name, value=name) for name in choices[:25]]

# --- 補助ロジック ---

def validate_and_get_dt(now: datetime, s_str: str, e_str: str):
    """時刻変換、日付跨ぎ、1時間以上の隙間チェック"""
    sh, sm = map(int, s_str.split(":"))
    eh, em = map(int, e_str.split(":"))
    s_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    e_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    
    if s_dt < now - timedelta(minutes=15): s_dt, e_dt = s_dt + timedelta(days=1), e_dt + timedelta(days=1)
    if e_dt <= s_dt: e_dt += timedelta(days=1)
    
    if e_dt - s_dt < timedelta(hours=1): return None, None
    return s_dt, e_dt

# --- コマンド ---

@client.tree.command(name="mealtogether")
@app_commands.describe(start="開始", end="終了", intras="Intra名")
@app_commands.autocomplete(start=time_autocomplete, end=time_autocomplete, intras=intra_autocomplete)
async def mealtogether(it: discord.Interaction, start: str, end: str, intras: str):
    await it.response.defer(ephemeral=True)
    if not client.api.validate_user(intras):
        return await it.followup.send(f"❌ User `{intras}` not found.")

    s_dt, e_dt = validate_and_get_dt(datetime.now(), start, end)
    if not s_dt:
        return await it.followup.send("❌ 最短でも1時間以上の時間枠を指定してください。")

    new_req = MealRequest(it.user.id, intras, s_dt, e_dt)
    if client.matcher.check_user_overlap(it.user.id, new_req):
        return await it.followup.send("⚠️ 既存の登録と重複しています。")

    matched = client.matcher.find_match(new_req)
    if matched:
        # マッチング通知処理（既存ロジックを継承）
        await it.followup.send(f"🎉 Matched with {matched.intra_name}!", ephemeral=False)
    else:
        client.matcher.add_request(new_req)
        await it.followup.send(f"✅ Added: {start}-{end}")

@client.tree.command(name="mealcancel")
async def mealcancel(it: discord.Interaction):
    count = client.matcher.cancel_user_requests(it.user.id)
    await it.response.send_message(f"✅ Canceled {count} requests.", ephemeral=True)

@client.event
async def on_ready(): print(f'Logged in as {client.user}')

if __name__ == "__main__": client.run(TOKEN)