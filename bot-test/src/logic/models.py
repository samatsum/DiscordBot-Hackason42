from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Literal

DETAIL_EMOJI_MAP = {
    "meal": "🍽️",
    "game": "🎮",
    "exercise": "🏃",
    "study": "📖",
}
# 辞書のキー ("meal", "game" 等) だけを自動でリスト化
VALID_DETAILS = list(DETAIL_EMOJI_MAP.keys())

# 型ヒント用
DetailType = Literal["meal", "game", "exercise", "study"]

@dataclass
class MatchRequest:
    discord_id: int
    intra_name: str
    start_time: datetime
    end_time: datetime
    detail: str  # シンプルに文字列(str)として扱う
    message_id: int | None = None

    @property
    def expire_at(self) -> datetime:
        return self.end_time - timedelta(minutes=15)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expire_at

    def overlaps_with(self, other: 'MatchRequest') -> bool:
        # 文字列同士の比較なので、Enumのような同期バグが起きません
        if self.detail != other.detail:
            return False
        latest_start = max(self.start_time, other.start_time)
        earliest_end = min(self.end_time, other.end_time)
        overlap_duration = earliest_end - latest_start
        return overlap_duration >= timedelta(hours=1)