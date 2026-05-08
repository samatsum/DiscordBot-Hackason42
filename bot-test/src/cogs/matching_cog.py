import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, time as dt_time
from logic.models import MatchRequest, VALID_DETAILS
from utils import time_utils, discord_utils

# --- オートコンプリート関数 (モジュールレベル) ---
async def start_auto(it: discord.Interaction, current: str):
    base = time_utils.get_rounded_time(datetime.now())
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(25)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t][:25]

async def end_auto(it: discord.Interaction, current: str):
    now = datetime.now()
    s_val = getattr(it.namespace, 'start', None)
    base = time_utils.get_rounded_time(now)
    if s_val and ":" in s_val:
        try:
            h, m = map(int, s_val.split(":"))
            temp_base = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if temp_base < now - timedelta(minutes=15): temp_base += timedelta(days=1)
            base = time_utils.get_rounded_time(temp_base)
        except ValueError: pass
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(4, 25)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t][:25]

async def detail_auto(it: discord.Interaction, current: str):
    """models.pyの定義に基づいてサジェストを生成"""
    return [app_commands.Choice(name=t, value=t) for t in VALID_DETAILS if current in t]

# --- Cogクラス ---
class MatchingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.cleanup_task.start()
        # 【追加】Discordサーバーへ最新のコマンド仕様(Enumの選択肢)を強制上書き同期する
        await self.bot.tree.sync()

    @tasks.loop(time=[dt_time(hour=h, minute=m) for h in range(24) for m in [0, 15, 30, 45]])
    async def cleanup_task(self):
        """期限切れリクエストの自動削除"""
        expired = self.bot.matcher.cleanup(datetime.now())
        for req in expired:
            for guild in self.bot.guilds:
                await discord_utils.delete_channel_message(guild, req)

    @app_commands.command(name="together", description="マッチング募集を開始します")
    @app_commands.describe(start="開始", end="終了", detail="目的を選択してください")
    @app_commands.autocomplete(start=start_auto, end=end_auto, detail=detail_auto)
    async def together(self, it: discord.Interaction, start: str, end: str, detail: str):
        await it.response.defer(ephemeral=True)

        # models.pyのリストに存在するかチェック
        if detail not in VALID_DETAILS:
            await it.delete_original_response()
            return await it.followup.send(f"❌ 無効な目的です。{VALID_DETAILS} から選択してください。", ephemeral=True)

        if not self.bot.api.validate_user(it.user.display_name):
            await it.delete_original_response()
            return await it.followup.send("❌ 表示名をIntraログイン名に合わせてください。", ephemeral=True)

        s_dt, e_dt = time_utils.parse_session_times(start, end, datetime.now())
        if e_dt - s_dt < timedelta(hours=1):
            await it.delete_original_response()
            return await it.followup.send("❌ 最短でも1時間以上の枠を指定してください。", ephemeral=True)

        req = MatchRequest(it.user.id, it.user.display_name, s_dt, e_dt, detail)

        async with self.bot.match_lock:
            if self.bot.matcher.check_user_overlap(it.user.id, req):
                await it.delete_original_response()
                return await it.followup.send("⚠️ 既に同時間帯に予約が入っています。", ephemeral=True)

            await self._execute_match(it, req)



    async def _execute_match(self, it: discord.Interaction, req: MatchRequest):
        """マッチングの実行と通知の振り分け"""
        matched = self.bot.matcher.find_match(req)
        if matched:
            await self._handle_match_success(it, req, matched)
        else:
            await self._handle_match_wait(it, req)

    async def _handle_match_success(self, it: discord.Interaction, my_req: MatchRequest, opp_req: MatchRequest):
        """マッチング成立時のオーケストレーション"""
        try:
            await discord_utils.delete_channel_message(it.guild, opp_req)
            await self._send_private_notifications(it, my_req, opp_req)
            await discord_utils.announce_match(it.guild, my_req, opp_req)
            await it.delete_original_response()
        except Exception as e:
            # 万が一裏側の処理でエラーが起きても、Bot全体をクラッシュさせない安全網
            print(f"マッチング後の処理でエラー発生: {e}")

    async def _send_private_notifications(self, it: discord.Interaction, my_req: MatchRequest, opp_req: MatchRequest):
            """DM通知のみを担当するサブ関数（共通の時間を計算する）"""
            opp_img = self.bot.api.get_user_image(opp_req.intra_name)
            my_img = self.bot.api.get_user_image(my_req.intra_name)

            # 【追加】マッチングが成立した「共通の時間帯」を計算
            match_start = max(my_req.start_time, opp_req.start_time)
            match_end = min(my_req.end_time, opp_req.end_time)

            # 自分（後攻）へのDM
            await discord_utils.send_match_dm(
                it.user, 
                opp_req.intra_name, 
                opp_img, 
                match_start, 
                match_end, 
                my_req.detail
            )

            # 相手（先攻）へのDM
            try:
                opp_user = await self.bot.fetch_user(opp_req.discord_id)
                if opp_user:
                    await discord_utils.send_match_dm(
                        opp_user, 
                        my_req.intra_name, 
                        my_img, 
                        match_start, 
                        match_end, 
                        my_req.detail
                    )
            except discord.HTTPException:
                pass

    async def _handle_match_wait(self, it: discord.Interaction, req: MatchRequest):
        """マッチング待機時の処理"""
        channel_exists = await discord_utils.post_to_matching_channel(it.guild, req)
        if not channel_exists:
            return await it.followup.send(f"❌ `#matching_{req.detail}` チャンネルが見つかりません。作成してください。")

        self.bot.matcher.add_request(req)
        await it.followup.send(f"✅ 追加しました: {req.start_time.strftime('%H:%M')}-{req.end_time.strftime('%H:%M')} ({req.detail})")

    @app_commands.command(name="cancel")
    async def cancel(self, it: discord.Interaction):
        cancelled = self.bot.matcher.cancel_user_requests(it.user.id)
        for req in cancelled:
            await discord_utils.delete_channel_message(it.guild, req)
        await it.response.send_message(f"✅ {len(cancelled)}件キャンセルしました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MatchingCog(bot))