from typing import List, Optional, Tuple
from datetime import datetime
from logic.models import MealRequest

class MatchManager:
    def __init__(self):
        # 待機行列（メモリ上での保持）
        self.queue: List[MealRequest] = []

    def cleanup(self, now: datetime):
        """期限切れのリクエストを $O(N)$ で排除"""
        self.queue = [req for req in self.queue if not req.is_expired(now)]

    def check_user_overlap(self, discord_id: int, new_req: MealRequest) -> bool:
        """同一ユーザー内の時間重複チェック"""
        user_requests = [req for req in self.queue if req.discord_id == discord_id]
        for req in user_requests:
            # 1分でも被ればTrue（重複あり）
            if max(req.start_time, new_req.start_time) < min(req.end_time, new_req.end_time):
                return True
        return False

    def find_match(self, new_req: MealRequest) -> Optional[MealRequest]:
        """FIFO形式で最初に見つかった適合相手を返す"""
        for i, existing_req in enumerate(self.queue):
            # 自分自身とのマッチングは除外
            if existing_req.discord_id == new_req.discord_id:
                continue
                
            if new_req.overlaps_with(existing_req):
                # マッチング成立：相手をリストから削除して返す
                return self.queue.pop(i)
        return None

    def add_request(self, req: MealRequest):
        """マッチしなかったリクエストを末尾に追加"""
        self.queue.append(req)

    def cancel_user_requests(self, discord_id: int) -> int:
        """特定のユーザーのリクエストを一括削除"""
        initial_count = len(self.queue)
        self.queue = [req for req in self.queue if req.discord_id != discord_id]
        return initial_count - len(self.queue)