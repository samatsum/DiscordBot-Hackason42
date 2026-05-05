import os
import discord
import asyncio
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
from datetime import datetime, timedelta, time as dt_time

from logic.models import MealRequest
from logic.matcher import MatchManager
from logic.api import FTAPIClient

load_dotenv()
TOKEN, GUILD_ID = os.getenv("DISCORD_TOKEN"), os.getenv("GUILD_ID")
UID, SECRET = os.getenv("FORTYTWO_APP_UID"), os.getenv("FORTYTWO_APP_SECRET")

class MealBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        super().__init__(intents=intents)
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

# --- DM送信ヘルパー ---
async def send_match_dm(user: discord.User, opponent_intra: str, image_url: str):
    embed = discord.Embed(
        title="🎉 マッチング成立！",
        description=f"**{opponent_intra}** さんとマッチングしました！",
        color=0x00ff00
    )
    if image_url:
        embed.set_image(url=image_url)
    try:
        await user.send(embed=embed)
    except:
        pass

# --- 共通ヘルパー関数・オートコンプリート (既存のまま) ---
def get_rounded_time(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    if dt.minute % 15 != 0:
        dt += timedelta(minutes=(15 - dt.minute % 15))
    return dt

async def start_auto(it: discord.Interaction, current: str):
    base = get_rounded_time(datetime.now())
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(25)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t][:25]

async def end_auto(it: discord.Interaction, current: str):
    now = datetime.now()
    s_val = getattr(it.namespace, 'start', None)
    base = get_rounded_time(now)
    if s_val and ":" in s_val:
        try:
            h, m = map(int, s_val.split(":"))
            temp_base = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if temp_base < now - timedelta(minutes=15): temp_base += timedelta(days=1)
            base = get_rounded_time(temp_base)
        except ValueError: pass
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(4, 42)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t][:25]

async def intra_auto(it: discord.Interaction, current: str):
    if not it.guild: return []
    members = it.guild.members
    matches = [m.display_name for m in members if current.lower() in m.display_name.lower()]
    matches = list(dict.fromkeys(matches))
    return [app_commands.Choice(name=m, value=m) for m in matches][:25]

# --- コマンド ---
@client.tree.command(name="mealtogether")
@app_commands.describe(start="開始", end="終了", intras="Intra名(Discord表示名)")
@app_commands.autocomplete(start=start_auto, end=end_auto, intras=intra_auto)
async def mealtogether(it: discord.Interaction, start: str, end: str, intras: str):
    await it.response.defer(ephemeral=True)
    
    # API検証
    if not client.api.validate_user(intras):
        return await it.followup.send(f"❌ User `{intras}` は42のIntra上に存在しません。")
    
    now = datetime.now()
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    s_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    e_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    
    if s_dt < now - timedelta(minutes=15): s_dt, e_dt = s_dt + timedelta(days=1), e_dt + timedelta(days=1)
    if e_dt <= s_dt: e_dt += timedelta(days=1)
    if e_dt - s_dt < timedelta(hours=1):
        return await it.followup.send("❌ 最短でも1時間以上の枠を指定してください。")

    req = MealRequest(it.user.id, intras, s_dt, e_dt)
    if client.matcher.check_user_overlap(it.user.id, req):
        return await it.followup.send("⚠️ 時間が重複しています。")

    matched = client.matcher.find_match(req)
    if matched:
        # 画像取得 (相手の画像を自分へ、自分の画像を相手へ)
        opp_image = client.api.get_user_image(matched.intra_name)
        my_image = client.api.get_user_image(intras)

        # 自分へのDM (相手の画像)
        await send_match_dm(it.user, matched.intra_name, opp_image)

        # 相手へのDM (自分の画像)
        try:
            opponent_user = await client.fetch_user(matched.discord_id)
            if opponent_user:
                await send_match_dm(opponent_user, intras, my_image)
        except:
            pass

        await it.followup.send(f"🎉 Matched with {matched.intra_name}! DMを確認してください。")
    else:
        client.matcher.add_request(req)
        await it.followup.send(f"✅ 追加しました: {start}-{end}")

@client.tree.command(name="mealcancel")
async def mealcancel(it: discord.Interaction):
    count = client.matcher.cancel_user_requests(it.user.id)
    await it.response.send_message(f"✅ {count}件キャンセルしました。", ephemeral=True)

if __name__ == "__main__":
    client.run(TOKEN)