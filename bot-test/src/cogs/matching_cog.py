import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from logic.models import MatchRequest
from utils import time_utils, discord_utils

class ParticipantSelectView(discord.ui.View):
    def __init__(self, original_it, cog, start, end, detail):
        super().__init__(timeout=60)
        self.original_it = original_it
        self.cog = cog
        self.start, self.end, self.detail = start, end, detail
        self.selected_members = [] # Memberオブジェクトのリストを保持

    @discord.ui.select(
        cls=discord.ui.UserSelect, 
        placeholder="メンバーを選択（最大24名）", 
        min_values=1, 
        max_values=24,
        row=0
    )
    async def select_participants(self, it: discord.Interaction, select: discord.ui.UserSelect):
        # 42生チェック済みのメンバーのみを保持
        self.selected_members = [
            m for m in select.values 
            if self.cog.bot.api.validate_user(m.display_name)
        ]
        names = ", ".join([m.display_name for m in self.selected_members])
        await it.response.edit_message(
            content=f"👥 選択中: **{names}**\n間違いなければ「決定」ボタンを、一人の場合は「ソロ」ボタンを押してください。",
            view=self
        )

    @discord.ui.button(label="この人数で決定する", style=discord.ButtonStyle.primary, row=1)
    async def confirm_button(self, it: discord.Interaction, button: discord.ui.Button):
        if not self.selected_members:
            return await it.response.send_message("❌ メンバーを選択してください。", ephemeral=True)
        await it.response.defer(ephemeral=True)
        await self.original_it.edit_original_response(content="✅ メンバーを確定しました。", view=None)
        await self.cog.process_matching(it, self.start, self.end, self.detail, self.selected_members)

    @discord.ui.button(label="自分一人で参加する", style=discord.ButtonStyle.grey, row=1)
    async def solo_button(self, it: discord.Interaction, button: discord.ui.Button):
        await it.response.defer(ephemeral=True)
        await self.original_it.edit_original_response(content="✅ ソロ参加で確定しました。", view=None)
        await self.cog.process_matching(it, self.start, self.end, self.detail, [])

class MatchingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="together", description="マッチング募集を開始します")
    @app_commands.describe(start="開始時間", end="終了時間", detail="目的を選択")
    @app_commands.autocomplete(start=time_utils.start_auto, end=time_utils.end_auto, detail=time_utils.detail_auto)
    async def together(self, it: discord.Interaction, start: str, end: str, detail: str):
        view = ParticipantSelectView(it, self, start, end, detail)
        await it.response.send_message("👥 一緒に参加するメンバーを選択してください：", view=view, ephemeral=True)

    async def process_matching(self, it: discord.Interaction, start: str, end: str, detail: str, others: list[discord.Member]):
        s_dt, e_dt = time_utils.parse_session_times(start, end, datetime.now())
        
        # IDと表示名の整理
        other_ids = [m.id for m in others]
        display_name = it.user.display_name
        if others:
            display_name += f" (+{len(others)} others)"
        
        # models.py で追加した other_discord_ids を渡す
        req = MatchRequest(it.user.id, display_name, other_ids, s_dt, e_dt, detail)

        async with self.bot.match_lock:
            if self.bot.matcher.check_user_overlap(it.user.id, req):
                return await it.followup.send("⚠️ 既に同時間帯に予約があります。", ephemeral=True)

            matched = self.bot.matcher.find_match(req)
            if matched:
                await self._handle_match_success(it, req, matched)
            else:
                await self._handle_match_wait(it, req)

    async def _handle_match_wait(self, it: discord.Interaction, req: MatchRequest):
        if await discord_utils.post_to_matching_channel(it.guild, req):
            self.bot.matcher.add_request(req)
            await it.followup.send(f"✅ 募集を開始しました！ ({req.start_time.strftime('%H:%M')}-)", ephemeral=True)
        else:
            await it.followup.send("❌ 掲示板が見つかりません。", ephemeral=True)

    async def _handle_match_success(self, it: discord.Interaction, my_req: MatchRequest, opp_req: MatchRequest):
        await discord_utils.delete_channel_message(it.guild, opp_req)
        
        # 顔写真取得用の代表者Intra名（カッコ内を除去）
        def get_rep(name): return name.split(" (")[0]
        my_img = self.bot.api.get_user_image(get_rep(my_req.intra_name))
        opp_img = self.bot.api.get_user_image(get_rep(opp_req.intra_name))

        # マッチングした共通の時間帯
        m_start, m_end = max(my_req.start_time, opp_req.start_time), min(my_req.end_time, opp_req.end_time)

        # 自分たち側（代表者 + Others）全員に通知
        for uid in [my_req.discord_id] + my_req.other_discord_ids:
            u = await self.bot.fetch_user(uid)
            await discord_utils.send_match_dm(u, opp_req.intra_name, opp_img, m_start, m_end, my_req.detail)

        # 相手側（代表者 + Others）全員に通知
        for uid in [opp_req.discord_id] + opp_req.other_discord_ids:
            u = await self.bot.fetch_user(uid)
            await discord_utils.send_match_dm(u, my_req.intra_name, my_img, m_start, m_end, my_req.detail)

        await discord_utils.announce_match(it.guild, my_req, opp_req)

    @app_commands.command(name="cancel")
    async def cancel(self, it: discord.Interaction):
        cancelled = self.bot.matcher.cancel_user_requests(it.user.id)
        for req in cancelled:
            await discord_utils.delete_channel_message(it.guild, req)
        await it.response.send_message(f"✅ {len(cancelled)}件キャンセルしました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MatchingCog(bot))