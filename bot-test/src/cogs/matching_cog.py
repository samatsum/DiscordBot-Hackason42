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


class ParticipantSelectView(discord.ui.View):
    def __init__(self, original_it, cog, start, end, detail):
        super().__init__(timeout=60)
        self.original_it = original_it
        self.cog = cog
        self.start = start
        self.end = end
        self.detail = detail

    # 【追加】ソロ参加ボタン：メニュー操作なしで即座に確定させる
    @discord.ui.button(label="自分一人で参加する", style=discord.ButtonStyle.grey, row=1)
    async def solo_button(self, it: discord.Interaction, button: discord.ui.Button):
        await it.response.defer(ephemeral=True)
        # UIを閉じ、空のリストを渡してマッチング処理へ
        await self.original_it.edit_original_response(content="✅ ソロ参加で確定しました。", view=None)
        await self.cog.process_matching(it, self.start, self.end, self.detail, [])

    # 複数人選択メニュー
    @discord.ui.select(
        cls=discord.ui.UserSelect, 
        placeholder="メンバーを選択（最大24名）", 
        min_values=1, 
        max_values=24,
        row=0
    )
    async def select_participants(self, it: discord.Interaction, select: discord.ui.UserSelect):
        # バリデーション済みの名前リストを作成
        selected_names = [m.display_name for m in select.values if self.cog.bot.api.validate_user(m.display_name)]
        
        await it.response.defer(ephemeral=True)
        await self.original_it.edit_original_response(content=f"✅ {len(selected_names)}名を指定して確定しました。", view=None)
        
        # 選択されたリストを渡してマッチング処理へ
        await self.cog.process_matching(it, self.start, self.end, self.detail, selected_names)

# --- 2. Cogクラス ---
class MatchingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="together", description="マッチング募集を開始します")
    @app_commands.describe(start="開始時間", end="終了時間", detail="目的を選択")
    @app_commands.autocomplete(
        start=time_utils.start_auto, 
        end=time_utils.end_auto, 
        detail=time_utils.detail_auto
    )
    async def together(self, it: discord.Interaction, start: str, end: str, detail: str):
        """第一段階：基本情報の入力とメンバー選択Viewの提示"""
        # ephemeral=True にすることで、この選択メニューは実行者にしか見えません
        view = ParticipantSelectView(it, self, start, end, detail)
        await it.response.send_message("👥 一緒に参加するメンバー（Others）を選択してください：", view=view, ephemeral=True)

    async def process_matching(self, it: discord.Interaction, start: str, end: str, detail: str, others: list[str]):
        """第二段階：実際のデータ作成とマッチング実行"""
        # 時間パース
        s_dt, e_dt = time_utils.parse_session_times(start, end, datetime.now())
        
        # 代表者のIntra名（it.user.display_name）と選択されたothersを統合
        # ※ ここでは代表者1人のRequestとして扱いますが、intra_nameに「samatum + 2 others」のように
        #    表示用の情報を付与するなどの拡張が可能です。
        
        display_name = f"{it.user.display_name} (with {', '.join(others)})" if others else it.user.display_name
        
        req = MatchRequest(it.user.id, display_name, s_dt, e_dt, detail)

        async with self.bot.match_lock:
            # 既存の重複チェック
            if self.bot.matcher.check_user_overlap(it.user.id, req):
                return await it.followup.send("⚠️ 既に同時間帯に予約が入っています。", ephemeral=True)

            # マッチング実行（既存ロジック）
            matched = self.bot.matcher.find_match(req)
            if matched:
                # 成立時の処理（既存の _handle_match_success 相当）
                await self._handle_match_success(it, req, matched)
            else:
                # 待機時の処理（既存の _handle_match_wait 相当）
                await self._handle_match_wait(it, req)


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