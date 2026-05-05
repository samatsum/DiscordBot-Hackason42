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

# 変数名をあなたの指定通りに修正
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
UID = os.getenv("FORTYTWO_APP_UID")
SECRET = os.getenv("FORTYTWO_APP_SECRET")

class MealBot(discord.Client):
    def __init__(self):
        # メンバー取得のためにIntentsを適切に設定
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

# --- オートコンプリート ---

async def time_autocomplete(it: discord.Interaction, current: str):
    now = datetime.now()
    base = now.replace(second=0, microsecond=0)
    if base.minute % 15 != 0:
        base += timedelta(minutes=(15 - base.minute % 15))
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(25)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t]

async def intra_autocomplete(it: discord.Interaction, current: str):
    """メンバー名(intra)をサジェスト。Valueにはintra名(username)を入れる"""
    if not it.guild: return []
    choices = []
    for m in it.guild.members:
        if current.lower() in m.name.lower() or (m.nick and current.lower() in m.nick.lower()):
            choices.append(app_commands.Choice(name=f"{m.display_name} ({m.name})", value=m.name))
    return choices[:25]

# --- 補助ロジック ---

async def send_dm(user_id, message):
    """エラーを分離してDMを送信"""
    try:
        user = await client.fetch_user(user_id)
        await user.send(message)
    except Exception as e:
        print(f"DM送信失敗 (User ID: {user_id}): {e}")

async def notify_match(it: discord.Interaction, new: MealRequest, old: MealRequest):
    """マッチング通知。一方の失敗が他方に影響しないよう分離"""
    s, e = max(new.start_time, old.start_time), min(new.end_time, old.end_time)
    t_range = f"{s.strftime('%H:%M')} - {e.strftime('%H:%M')}"
    
    # 待機者へ通知
    msg_to_old = f"🎉 **MealTogether!**\n`{t_range}` に `{new.intra_name}` さんとマッチしました！"
    await send_dm(old.discord_id, msg_to_old)
    
    # 実行者へ通知 (it.userを直接利用)
    try:
        await it.user.send(f"🎉 **MealTogether!**\n`{t_range}` に `{old.intra_name}` さんとマッチしました！")
    except: pass

    await it.followup.send(f"🎉 `{new.intra_name}` さんと `{old.intra_name}` さんのマッチが成立しました！", ephemeral=False)

# --- コマンド ---

@client.tree.command(name="mealtogether", description="Meal Together matching!")
@app_commands.describe(start="開始(15分刻み)", end="終了(15分刻み)", intras="Intra名")
@app_commands.autocomplete(start=time_autocomplete, end=time_autocomplete, intras=intra_autocomplete)
async def mealtogether(it: discord.Interaction, start: str, end: str, intras: str):
    await it.response.defer(ephemeral=True)
    if not client.api.validate_user(intras):
        return await it.followup.send(f"❌ User `{intras}` not found.")

    # 時刻変換と1時間チェック
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
        return await it.followup.send("⚠️ 既存の登録と重複しています。")

    matched = client.matcher.find_match(new_req)
    if matched:
        await notify_match(it, new_req, matched)
    else:
        client.matcher.add_request(new_req)
        await it.followup.send(f"✅ 待機列に追加: {start}-{end}")

@client.tree.command(name="mealcancel", description="Cancel your requests")
async def mealcancel(it: discord.Interaction):
    count = client.matcher.cancel_user_requests(it.user.id)
    await it.response.send_message(f"✅ {count}件キャンセルしました。", ephemeral=True)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN is not set.")
        exit(1)
    client.run(TOKEN)