from datetime import datetime, timedelta

def get_rounded_time(dt: datetime) -> datetime:
    """
    時刻を15分単位で切り上げる。
    計算量: O(1)
    """
    dt = dt.replace(second=0, microsecond=0)
    if dt.minute % 15 != 0:
        dt += timedelta(minutes=(15 - dt.minute % 15))
    return dt

def parse_session_times(start_str: str, end_str: str, now: datetime) -> tuple[datetime, datetime]:
    """
    文字列の時刻をdatetimeに変換し、日付の跨ぎを調整する。
    """
    sh, sm = map(int, start_str.split(":"))
    eh, em = map(int, end_str.split(":"))
    
    s_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    e_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)

    # 過去の時刻なら翌日に回す (15分のバッファ)
    if s_dt < now - timedelta(minutes=15):
        s_dt += timedelta(days=1)
        e_dt += timedelta(days=1)
    
    # 終了時刻が開始より前なら翌日とする
    if e_dt <= s_dt:
        e_dt += timedelta(days=1)
        
    return s_dt, e_dt