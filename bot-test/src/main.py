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

# 変数名はあなたの指定とリポジトリを優先
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
UID = os.getenv("FORTYTWO_APP_UID")
SECRET = os.getenv("FORTYTWO_APP_SECRET")

class MealBot(discord.Client):
    def __init__(self):
        # メンバー取得のためにIntentsを設定
        intents = discord.Intents.default()
        intents.members = True 
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.matcher = MatchManager()
        self.api = FTAPIClient(UID, SECRET)

    async def setup_hook(self):
        self.cleanup_task.start()
        guild = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None
        if guild:
            self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    @tasks.loop(time=[dt_time(hour=h, minute=m) for h in range(24) for m in [0, 15, 30, 45]])
    async def cleanup_task(self):
        self.matcher.cleanup(datetime.now())

client = MealBot()

# --- 補助ロジック (20行以内) ---

def get_base_time(now: datetime):
    """現在時刻を15分単位で切り上げた基準"""
    base = now.replace(second=0, microsecond=0)
    if base.minute % 15 != 0:
        base += timedelta(minutes=(15 - base.minute % 15))
    return base

# --- オートコンプリート ---

async def start_time_autocomplete(it: discord.Interaction, current: str):
    base = get_base_time(datetime.now())
    # 10時間分の候補(42件)を生成
    times = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(42)]
    return [app_commands.Choice(name=t, value=t) for t in times if current in t][:25]

async def end_time_autocomplete(it: discord.Interaction, current: str):
    now = datetime.now()
    # 属性の存在を安全に確認 (Noneや属性欠如に対応)
    start_val = getattr(it.namespace, 'start', None)
    
    if start_val and ":" in start_val:
        sh, sm = map(int, start_val.split(":"))
        base = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if base < now - timedelta(minutes=15): base += timedelta(days=1)
    else:
        base = get_base_time(now)

    # Startの1時間後(i=4)から、全体で10時間枠に収まる範囲を表示
    times = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(4, 42)]
    return [app_commands.Choice(name=t, value=t) for t in times if current in t][:25]

async def intra_autocomplete(it: discord.Interaction, current: str):
    # 1文字も入力されていない場合はAPI負荷軽減のため空リストを返す
    if not current or len(current.strip()) == 0: return []
    logins = client.api.search_users(current)
    return [app_commands.Choice(name=login, value=login) for login in logins]

# --- メインコマンド ---

@client.tree.command(name="mealtogether", description="Meal Together matching!")
@app_commands.describe(start="開始時間", end="終了時間", intras="Intra名")
@app_commands.autocomplete(start=start_time_autocomplete, end=end_time_autocomplete, intras=intra_autocomplete)
async def mealtogether(it: discord.Interaction, start: str, end: str, intras: str):
    await it.response.defer(ephemeral=True)
    if not client.api.validate_user(intras):
        return await it.followup.send(f"❌ User `{intras}` not found.")

    now = datetime.now()
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    s_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    e_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    
    if s_dt < now - timedelta(minutes=15): s_dt, e_dt = s_dt + timedelta(days=1), e_dt + timedelta(days=1)
    if e_dt <= s_dt: e_dt += timedelta(days=1)
    
    if e_dt - s_dt < timedelta(hours=1):
        return await it.followup.send("❌ 最短でも1時間以上の枠を指定してください。")

    new_req = MealRequest(it.user.id, intras, s_dt, e_dt)
    if client.matcher.check_user_overlap(it.user.id, new_req):
        return await it.followup.send("⚠️ 時間が重複しています。")

    matched = client.matcher.find_match(new_req)
    if matched:
        # 相互DM通知ロジック (notify_match等は別途実装済みのものを想定)
        await it.followup.send(f"🎉 Matched with {matched.intra_name}!", ephemeral=False)
    else:
        client.matcher.add_request(new_req)
        await it.followup.send(f"✅ 追加しました: {start}-{end}")

if __name__ == "__main__":
    client.run(TOKEN)