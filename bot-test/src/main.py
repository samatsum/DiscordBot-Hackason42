import os
import re
from datetime import datetime, timedelta, time as dt_time
import discord
from discord.ext import tasks
from discord import app_commands
from dotenv import load_dotenv

# 自作ロジック
from logic.models import MealRequest
from logic.matcher import MatchManager
from logic.api import FTAPIClient

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
FT_UID = os.getenv("FORTYTWO_APP_UID")
FT_SECRET = os.getenv("FORTYTWO_APP_SECRET")

CLEANUP_TIMES = [dt_time(hour=h, minute=m) for h in range(24) for m in [0, 15, 30, 45]]

class MealBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.matcher = MatchManager()
        # APIクライアントの初期化
        self.api = FTAPIClient(FT_UID, FT_SECRET)

    async def setup_hook(self):
        self.cleanup_task.start()
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    @tasks.loop(time=CLEANUP_TIMES)
    async def cleanup_task(self):
        now = datetime.now()
        self.matcher.cleanup(now)

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.wait_until_ready()

client = MealBot()

# --- 補助関数 ---

def parse_time_string(time_str: str, base_time: datetime) -> tuple[datetime, datetime]:
    match = re.match(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$", time_str)
    if not match:
        raise ValueError("形式エラー: `HH:MM-HH:MM`で入力してください。")
    sh, sm, eh, em = map(int, match.groups())
    start_dt = base_time.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end_dt = base_time.replace(hour=eh, minute=em, second=0, microsecond=0)
    if start_dt < base_time:
        start_dt += timedelta(days=1)
        end_dt += timedelta(days=1)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt

# --- コマンド定義 ---

@client.tree.command(name="mealtogether", description="食事マッチングの待機列に入ります")
@app_commands.describe(time="希望時間帯 (例: 13:00-15:00)", intra="あなたのIntra名")
async def cmd_mealtogether(interaction: discord.Interaction, time: str, intra: str):
    await interaction.response.defer(ephemeral=True) # API照合に時間がかかるため先にdefer
    
    now = datetime.now()
    
    # 1. 42 APIによるIntra名バリデーション
    if not client.api.validate_user(intra):
        await interaction.followup.send(f"❌ Intra名 `{intra}` は見つかりませんでした。正しい名称を入力してください。")
        return

    # 2. 時間のパースとバリデーション
    try:
        start_dt, end_dt = parse_time_string(time, now)
    except ValueError as e:
        await interaction.followup.send(str(e))
        return

    if start_dt.minute % 15 != 0 or end_dt.minute % 15 != 0:
        await interaction.followup.send("時刻は15分単位で指定してください。")
        return

    # 3. リクエスト作成と重複チェック
    new_req = MealRequest(interaction.user.id, intra, start_dt, end_dt)
    if client.matcher.check_user_overlap(interaction.user.id, new_req):
        await interaction.followup.send("既に登録しているリクエストと時間が重複しています。")
        return

    # 4. マッチング判定
    matched_req = client.matcher.find_match(new_req)

    if matched_req:
        overlap_start = max(new_req.start_time, matched_req.start_time)
        overlap_end = min(new_req.end_time, matched_req.end_time)
        time_range = f"{overlap_start.strftime('%H:%M')} - {overlap_end.strftime('%H:%M')}"

        # 相互通知
        for uid, target_intra in [(matched_req.discord_id, intra), (interaction.user.id, matched_req.intra_name)]:
            try:
                user = await client.fetch_user(uid)
                await user.send(f"🎉 **MealTogether!**\n`{time_range}` に `{target_intra}` さんとマッチしました！")
            except:
                pass
        
        # interactionへの応答を公開設定に変更して送信
        await interaction.followup.send(f"🎉 `{intra}` さんと `{matched_req.intra_name}` さんのマッチが成立しました！", ephemeral=False)
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
    print(f'Logged in as {client.user}')

if __name__ == "__main__":
    client.run(TOKEN)