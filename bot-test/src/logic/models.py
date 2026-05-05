from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class MealRequest:
    discord_id: int      # セキュリティ用
    intra_name: str      # 表示・通知用
    start_time: datetime
    end_time: datetime

    @property
    def expire_at(self) -> datetime:
        """削除基準時刻（終了時刻の15分前）"""
        return self.end_time - timedelta(minutes=15)

    def is_expired(self, now: datetime) -> bool:
        """現在時刻が削除基準を過ぎているか判定"""
        return now >= self.expire_at

    def overlaps_with(self, other: 'MealRequest') -> bool:
        """
        2つのリクエストが「1時間以上」被っているか判定
        アルゴリズム: max(start) と min(end) の差分を計算
        """
        latest_start = max(self.start_time, other.start_time)
        earliest_end = min(self.end_time, other.end_time)
        
        overlap_duration = earliest_end - latest_start
        return overlap_duration >= timedelta(hours=1)