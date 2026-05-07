from typing import List, Optional
from datetime import datetime
from logic.models import MealRequest

class MatchManager:
    def __init__(self):
        self.queue: List[MealRequest] = []

    def cleanup(self, now: datetime) -> List[MealRequest]:
        """
        期限切れリクエストをキューから取り除き、削除対象を返す
        """
        expired = [req for req in self.queue if req.is_expired(now)]
        self.queue = [req for req in self.queue if not req.is_expired(now)]
        return expired

    def check_user_overlap(self, discord_id: int, new_req: MealRequest) -> bool:
        """
        1人のDiscordユーザーが複数の予約（別Intra名含む）を被せて入れるのを防ぐ
        """
        user_requests = [req for req in self.queue if req.discord_id == discord_id]
        for req in user_requests:
            if max(req.start_time, new_req.start_time) < min(req.end_time, new_req.end_time):
                return True
        return False

    def find_match(self, new_req: MealRequest) -> Optional[MealRequest]:
        """
        自分以外のユーザー（異なるDiscord ID）とのみマッチングさせる
        """
        for i, existing_req in enumerate(self.queue):
            # 自分自身（同一Discord ID）はスキップ
            if existing_req.discord_id == new_req.discord_id:
                continue
            if new_req.overlaps_with(existing_req):
                return self.queue.pop(i)
        return None

    def add_request(self, req: MealRequest):
        self.queue.append(req)

    def cancel_user_requests(self, discord_id: int) -> List[MealRequest]:
        """キャンセルされたリクエストを返す（チャンネル投稿削除のため）"""
        cancelled = [req for req in self.queue if req.discord_id == discord_id]
        self.queue = [req for req in self.queue if req.discord_id != discord_id]
        return cancelled
