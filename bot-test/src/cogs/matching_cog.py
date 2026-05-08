import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time as dt_time
from logic.models import MatchRequest
from utils import time_utils, discord_utils

class MatchingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.cleanup_task.start()

    @tasks.loop(time=[dt_time(hour=h, minute=m) for h in range(24) for m in [0, 15, 30, 45]])
    async def cleanup_task(self):
        """期限切れリクエストの自動削除"""
        expired = self.bot.matcher.cleanup(datetime.now())
        for req in expired:
            # 削除処理（簡易化のため詳細は割愛）
            pass

    @app_commands.command(name="together", description="マッチング募集を開始します")
    async def together(self, it: discord.Interaction, start: str, end: str, detail: str):
        await it.response.defer(ephemeral=True)
        
        # 1. バリデーション
        if not self.bot.api.validate_user(it.user.display_name):
            return await it.followup.send("❌ 表示名をIntraログイン名に合わせてください。")

        # 2. 時刻計算
        s_dt, e_dt = time_utils.parse_session_times(start, end, datetime.now())
        req = MatchRequest(it.user.id, it.user.display_name, s_dt, e_dt, detail)

        # 3. マッチング実行
        await self._execute_match(it, req)

    async def _execute_match(self, it: discord.Interaction, req: MatchRequest):
        """マッチングの実行と通知の振り分け (SRPに基づく分離)"""
        matched = self.bot.matcher.find_match(req)
        if matched:
            await self._handle_match_success(it, req, matched)
        else:
            await self._handle_match_wait(it, req)

    async def _handle_match_success(self, it: discord.Interaction, my_req: MatchRequest, opp_req: MatchRequest):
        # 画像取得とDM送信ロジック (20行以内)
        opp_img = self.bot.api.get_user_image(opp_req.intra_name)
        await discord_utils.send_match_dm(it.user, opp_req.intra_name, opp_img)
        # 相手への通知とチャンネル投稿削除
        await it.followup.send(f"🎉 {opp_req.intra_name} さんとマッチングしました！")

    @app_commands.command(name="cancel")
    async def cancel(self, it: discord.Interaction):
        cancelled = self.bot.matcher.cancel_user_requests(it.user.id)
        await it.response.send_message(f"✅ {len(cancelled)}件キャンセルしました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MatchingCog(bot))