import time
import requests
from typing import Optional

class FTAPIClient:
    def __init__(self, uid: str, secret: str):
        self.uid = uid
        self.secret = secret
        self.token: Optional[str] = None
        self.expire_time: float = 0

    def _fetch_token(self) -> bool:
        """Client Credentials Flow でアクセストークンを取得"""
        url = "https://api.intra.42.fr/oauth/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.uid,
            "client_secret": self.secret
        }
        response = requests.post(url, data=data)
        if response.status_code != 200:
            return False
        
        res_json = response.json()
        self.token = res_json["access_token"]
        self.expire_time = time.time() + res_json["expires_in"]
        return True

    def _get_valid_token(self) -> Optional[str]:
        """有効なトークンを返す（期限切れなら再取得）"""
        if not self.token or time.time() >= self.expire_time:
            if not self._fetch_token():
                return None
        return self.token

    def validate_user(self, intra_name: str) -> bool:
        """Intra名が42 API上に存在するか確認"""
        token = self._get_valid_token()
        if not token:
            return False

        url = f"https://api.intra.42.fr/v2/users/{intra_name}"
        headers = {"Authorization": f"Bearer {token}"}
        
        # 200: 存在, 404: 存在しない, その他: エラー
        response = requests.get(url, headers=headers)
        return response.status_code == 200