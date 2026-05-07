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

DETAIL_CHANNEL_MAP = {
    "meal":     "matching_meal",
    "game":     "matching_game",
    "exercise": "matching_exercise",
}

DETAIL_EMOJI_MAP = {
    "meal":     "🍽️",
    "game":     "🎮",
    "exercise": "🏃",
}

class MealBot(discord.Client):
    def __init__(self):
        # membersインテントが必須(Discordのメンバーリスト取得のため)
        intents = discord.Intents.default()
        intents.members = True
        # --- DEBUG: ping/pong（どのBotが反応しているか）。OFFにする時は次の1行をコメントし、on_message の DEBUG ブロックもコメント ---
        intents.message_content = True
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
        expired_requests = self.matcher.cleanup(datetime.now())
        guild = discord.utils.get(self.guilds)
        if guild:
            for req in expired_requests:
                await delete_channel_message(guild, req)

    # --- DEBUG: ping だけ（PINGPONG と同様の完全一致）。OFF: このメソッド全体をコメント。__init__ の message_content 行もコメント ---
    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        if message.content == "ping":
            await message.channel.send("pong-torinoue3")

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

# --- チャンネル投稿ヘルパー ---
async def post_to_matching_channel(guild: discord.Guild, req: MealRequest) -> bool:
    """
    対応するマッチングチャンネルに投稿する。
    チャンネルが存在しない場合はFalseを返す。
    成功した場合はreq.message_idを設定してTrueを返す。
    """
    channel_name = DETAIL_CHANNEL_MAP[req.detail]
    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if not channel:
        return False

    emoji = DETAIL_EMOJI_MAP[req.detail]
    embed = discord.Embed(
        title=f"{emoji} マッチング募集",
        color=0x3498db
    )
    embed.add_field(name="👤 ユーザー", value=req.intra_name, inline=True)
    embed.add_field(name="🕐 時間帯", value=f"{req.start_time.strftime('%H:%M')} - {req.end_time.strftime('%H:%M')}", inline=True)
    embed.add_field(name="📝 目的", value=req.detail, inline=True)

    msg = await channel.send(embed=embed)
    req.message_id = msg.id
    return True

async def delete_channel_message(guild: discord.Guild, req: MealRequest):
    """
    チャンネルに投稿されたマッチング情報を削除する。
    メッセージが既に存在しない場合もエラーを吐かない。
    """
    if not req.message_id:
        return

    channel_name = DETAIL_CHANNEL_MAP[req.detail]
    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if not channel:
        return

    try:
        msg = await channel.fetch_message(req.message_id)
        await msg.delete()
    except (discord.NotFound, discord.HTTPException):
        pass

# --- 共通ヘルパー関数 ---
def get_rounded_time(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    if dt.minute % 15 != 0:
        dt += timedelta(minutes=(15 - dt.minute % 15))
    return dt

# --- オートコンプリート ---
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

async def detail_auto(it: discord.Interaction, current: str):
    options = ["meal", "game", "exercise"]
    return [app_commands.Choice(name=o, value=o) for o in options if current in o]

# --- コマンド ---
@client.tree.command(name="mealtogether")
@app_commands.describe(start="開始", end="終了", detail="目的 (meal / game / exercise)")
@app_commands.autocomplete(start=start_auto, end=end_auto, detail=detail_auto)
async def mealtogether(it: discord.Interaction, start: str, end: str, detail: str):
    await it.response.defer(ephemeral=True)

    if detail not in ("meal", "game", "exercise"):
        return await it.followup.send("❌ detail は meal / game / exercise のいずれかを選択してください。")

    # 自身の表示名(display_name)をIntra名として使用
    my_intra = it.user.display_name

    # API検証: 表示名が42のIntra上に実在するか確認
    if not client.api.validate_user(my_intra):
        return await it.followup.send(f"❌ あなたの表示名 `{my_intra}` は42のIntra上に存在しません。表示名をIntraログイン名に合わせてください。")

    now = datetime.now()
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    s_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    e_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)

    if s_dt < now - timedelta(minutes=15): s_dt, e_dt = s_dt + timedelta(days=1), e_dt + timedelta(days=1)
    if e_dt <= s_dt: e_dt += timedelta(days=1)
    if e_dt - s_dt < timedelta(hours=1):
        return await it.followup.send("❌ 最短でも1時間以上の枠を指定してください。")

    req = MealRequest(it.user.id, my_intra, s_dt, e_dt, detail)

    # 同一人物(Discord ID)の重複チェック
    if client.matcher.check_user_overlap(it.user.id, req):
        return await it.followup.send("⚠️ 既に同時間帯に予約が入っています。")

    matched = client.matcher.find_match(req)
    if matched:
        # 画像取得処理
        opp_image = client.api.get_user_image(matched.intra_name)
        my_image = client.api.get_user_image(my_intra)

        # 自分へのDM (相手の画像)
        await send_match_dm(it.user, matched.intra_name, opp_image)

        # 相手へのDM (自分の画像)
        try:
            opponent_user = await client.fetch_user(matched.discord_id)
            if opponent_user:
                await send_match_dm(opponent_user, my_intra, my_image)
        except:
            pass

        # マッチング成立: 相手のチャンネル投稿を削除
        await delete_channel_message(it.guild, matched)

        await it.followup.send(f"🎉 Matched with {matched.intra_name}! DMを確認してください。")
    else:
        # チャンネルへ投稿
        channel_exists = await post_to_matching_channel(it.guild, req)
        if not channel_exists:
            channel_name = DETAIL_CHANNEL_MAP[detail]
            return await it.followup.send(f"❌ `#{channel_name}` チャンネルが見つかりません。サーバー管理者に連絡してください。")

        client.matcher.add_request(req)
        await it.followup.send(f"✅ 追加しました: {start}-{end} ({detail})")

@client.tree.command(name="mealcancel")
async def mealcancel(it: discord.Interaction):
    cancelled = client.matcher.cancel_user_requests(it.user.id)
    for req in cancelled:
        await delete_channel_message(it.guild, req)
    await it.response.send_message(f"✅ {len(cancelled)}件キャンセルしました。", ephemeral=True)

if __name__ == "__main__":
    client.run(TOKEN)
