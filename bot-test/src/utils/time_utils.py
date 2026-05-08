import discord
from discord import app_commands
from datetime import datetime, timedelta
from logic.models import VALID_DETAILS

def get_rounded_time(dt: datetime) -> datetime:
    """15分単位で切り上げた時間を返す。時間計算量: O(1)"""
    minutes = (dt.minute // 15 + 1) * 15
    return dt.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)

async def start_auto(it: discord.Interaction, current: str):
    """開始時間の候補生成。O(N)"""
    base = get_rounded_time(datetime.now())
    # 15分刻みで24件（6時間分）の候補を表示
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(24)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t][:25]

async def end_auto(it: discord.Interaction, current: str):
    """終了時間の候補生成。開始時間の1時間後からサジェストする。"""
    now = datetime.now()
    # 既に入力された 'start' の値を取得
    s_val = getattr(it.namespace, 'start', None)
    
    base = get_rounded_time(now)
    if s_val and ":" in s_val:
        try:
            h, m = map(int, s_val.split(":"))
            temp_base = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if temp_base < now - timedelta(minutes=15):
                temp_base += timedelta(days=1)
            base = get_rounded_time(temp_base)
        except ValueError: 
            pass

    # 1時間後（15分×4）からサジェスト
    choices = [(base + timedelta(minutes=i * 15)).strftime("%H:%M") for i in range(4, 25)]
    return [app_commands.Choice(name=t, value=t) for t in choices if current in t][:25]

async def detail_auto(it: discord.Interaction, current: str):
    """目的の候補生成。models.py の定義を参照。"""
    return [app_commands.Choice(name=t, value=t) for t in VALID_DETAILS if current in t]

def parse_session_times(start_str: str, end_str: str, now: datetime):
    """文字列を datetime に変換する（既存ロジック）"""
    def to_dt(s: str):
        h, m = map(int, s.split(":"))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if dt < now - timedelta(minutes=15):
            dt += timedelta(days=1)
        return dt
    return to_dt(start_str), to_dt(end_str)