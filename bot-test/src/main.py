import os
import re
from datetime import datetime, timedelta, time as dt_time
import discord
from discord.ext import tasks
from discord import app_commands
from dotenv import load_dotenv

# 自作ロジックのインポート
from logic.models import MealRequest
from logic.matcher import MatchManager

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# --- 効率化：15分単位の実行時刻リストを作成 (24時間 * 4回 = 96ポイント) ---
CLEANUP_TIMES = [
    dt_time(hour=h, minute=m)
    for h in range(24)
    for m in [0, 15, 30, 45]
]

class MealBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.matcher = MatchManager()

    async def setup_hook(self):
        # 指定した時刻リストに基づき、バックグラウンドタスクを開始
        self.cleanup_task.start()
        
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Commands synced to Guild: {GUILD_ID}")
        else:
            await self.tree.sync()
            print("Commands synced globally.")

    # 15分ごとの壁時計時刻（Wall-clock time）に合わせて実行
    @tasks.loop(time=CLEANUP_TIMES)
    async def cleanup_task(self):
        """15分単位で期限切れリクエストを一括排除"""
        now = datetime.now()
        initial_count = len(self.matcher.queue)
        self.matcher.cleanup(now)
        final_count = len(self.matcher.queue)
        if initial_count != final_count:
            print(f"[{now.strftime('%H:%M')}] Cleanup: Removed {initial_count - final_count} expired requests.")

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.wait_until_ready()

client = MealBot()

# --- 補助関数 ---

def parse_time_string(time_str: str, base_time: datetime) -> tuple[datetime, datetime]:
    match = re.match(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$", time_str)
    if not match:
        raise ValueError("形式が正しくありません。`HH:MM-HH:MM`の形式で入力してください。")

    sh, sm, eh, em = map(int, match.groups())
    if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59):
         raise ValueError("時刻は00:00から23:59の間で指定してください。")

    start_dt = base_time.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end_dt = base_time.replace(hour=eh, minute=em, second=0, microsecond=0)

    if start_dt < base_time:
        start_dt += timedelta(days=1)
        end_dt += timedelta(days=1)

    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return start_dt, end_dt

def get_base_time(now: datetime) -> datetime:
    base = now.replace(second=0, microsecond=0)
    if base.minute % 15 != 0:
        base += timedelta(minutes=(15 - base.minute % 15))
    return base

# --- コマンド定義 ---

@client.tree.command(name="mealtogether", description="食事マッチングの待機列に入ります")
@app_commands.describe(time="希望時間帯 (例: 13:00-15:00)", intra="あなたのIntra名")
async def cmd_mealtogether(interaction: discord.Interaction, time: str, intra: str):
    now = datetime.now()
    base_time = get_base_time(now)

    try:
        start_dt, end_dt = parse_time_string(time, now)
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return

    if start_dt.minute % 15 != 0 or end_dt.minute % 15 != 0:
        await interaction.response.send_message("時刻は15分単位で指定してください。", ephemeral=True)
        return

    if end_dt > base_time + timedelta(hours=6):
        await interaction.response.send_message(f"指定可能な範囲は、{base_time.strftime('%H:%M')} から6時間以内です。", ephemeral=True)
        return
        
    if now >= (end_dt - timedelta(minutes=15)):
        await interaction.response.send_message("指定された時間帯は既に有効期限（終了時刻の15分前）を過ぎています。", ephemeral=True)
        return

    new_req = MealRequest(
        discord_id=interaction.user.id,
        intra_name=intra,
        start_time=start_dt,
        end_time=end_dt
    )

    if client.matcher.check_user_overlap(interaction.user.id, new_req):
        await interaction.response.send_message("既に登録しているリクエストと時間が重複しています。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    matched_req = client.matcher.find_match(new_req)

    if matched_req:
        overlap_start = max(new_req.start_time, matched_req.start_time)
        overlap_end = min(new_req.end_time, matched_req.end_time)
        time_str = f"{overlap_start.strftime('%H:%M')} - {overlap_end.strftime('%H:%M')}"

        try:
            target_user = await client.fetch_user(matched_req.discord_id)
            await target_user.send(f"🎉 **MealTogether!**\n`{time_str}` に `{new_req.intra_name}` さんとマッチングしました！")
        except:
            await interaction.followup.send(f"⚠️ 相手への通知に失敗しました。")

        try:
            await interaction.user.send(f"🎉 **MealTogether!**\n`{time_str}` に `{matched_req.intra_name}` さんとマッチングしました！")
        except:
             pass

        await interaction.followup.send(f"🎉 `{new_req.intra_name}` さんと `{matched_req.intra_name}` さんのマッチが成立しました！")
    else:
        client.matcher.add_request(new_req)
        await interaction.followup.send(f"✅ 待機列に追加しました。({start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')})")

@client.tree.command(name="mealcancel", description="自分のリクエストをすべてキャンセルします")
async def cmd_mealcancel(interaction: discord.Interaction):
    canceled_count = client.matcher.cancel_user_requests(interaction.user.id)
    msg = f"✅ {canceled_count} 件キャンセルしました。" if canceled_count > 0 else "❌ キャンセル対象がありません。"
    await interaction.response.send_message(msg, ephemeral=True)

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')

if __name__ == "__main__":
    client.run(TOKEN)
