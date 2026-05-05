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
        super().__init__(intents=discord.Intents.default())
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

# スマホ用オートコンプリート
async def time_autocomplete(it: discord.Interaction, current: str):
    now = datetime.now()
    base = now.replace(second=0, microsecond=0)
    if base.minute % 15 != 0:
        base += timedelta(minutes=(15 - base.minute % 15))
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(25)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t]

# 通知用
async def notify(it: discord.Interaction, new: MealRequest, old: MealRequest):
    s, e = max(new.start_time, old.start_time), min(new.end_time, old.end_time)
    t_range = f"{s.strftime('%H:%M')} - {e.strftime('%H:%M')}"
    for uid, target in [(old.discord_id, new.intra_name), (it.user.id, old.intra_name)]:
        try:
            u = await client.fetch_user(uid)
            await u.send(f"🎉 **MealTogether!** {t_range} with {target}")
        except: pass
    await it.followup.send(f"🎉 {new.intra_name} and {old.intra_name} matched!", ephemeral=False)

@client.tree.command(name="mealtogether", description="meal together!")
@app_commands.describe(start="13:00", end="15:00", intras="samatsum")
@app_commands.autocomplete(start=time_autocomplete, end=time_autocomplete)
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

    new_req = MealRequest(it.user.id, intras, s_dt, e_dt)
    if client.matcher.check_user_overlap(it.user.id, new_req):
        return await it.followup.send("⚠️ Time overlap with existing request.")

    matched = client.matcher.find_match(new_req)
    if matched:
        await notify(it, new_req, matched)
    else:
        client.matcher.add_request(new_req)
        await it.followup.send(f"✅ Added: {start}-{end}")

@client.tree.command(name="mealcancel", description="cancel your requests")
async def mealcancel(it: discord.Interaction):
    count = client.matcher.cancel_user_requests(it.user.id)
    await it.response.send_message(f"✅ Canceled {count} requests.", ephemeral=True)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

if __name__ == "__main__":
    client.run(TOKEN)