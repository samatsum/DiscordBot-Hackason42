from typing import List, Optional
from datetime import datetime
from logic.models import MealRequest

class MatchManager:
    def __init__(self):
        self.queue: List[MealRequest] = []

    def cleanup(self, now: datetime):
        self.queue = [req for req in self.queue if not req.is_expired(now)]

    def check_user_overlap(self, discord_id: int, new_req: MealRequest) -> bool:
        user_requests = [req for req in self.queue if req.discord_id == discord_id]
        for req in user_requests:
            if max(req.start_time, new_req.start_time) < min(req.end_time, new_req.end_time):
                return True
        return False

    def find_match(self, new_req: MealRequest) -> Optional[MealRequest]:
        for i, existing_req in enumerate(self.queue):
            if existing_req.discord_id == new_req.discord_id:
                continue
            if new_req.overlaps_with(existing_req):
                return self.queue.pop(i)
        return None

    def add_request(self, req: MealRequest):
        self.queue.append(req)

    def cancel_user_requests(self, discord_id: int) -> int:
        initial_count = len(self.queue)
        self.queue = [req for req in self.queue if req.discord_id != discord_id]
        return initial_count - len(self.queue)