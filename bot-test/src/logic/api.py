import time
import requests

class FTAPIClient:
    def __init__(self, uid, secret):
        self.uid, self.secret = uid, secret
        self.token, self.expire_time = None, 0

    def _get_token(self):
        if not self.token or time.time() >= self.expire_time:
            url = "https://api.intra.42.fr/oauth/token"
            data = {"grant_type": "client_credentials", "client_id": self.uid, "client_secret": self.secret}
            res = requests.post(url, data=data)
            if res.status_code == 200:
                self.token = res.json()["access_token"]
                self.expire_time = time.time() + res.json()["expires_in"]
        return self.token

    def validate_user(self, login):
        """サジェストはDiscordに任せるが、本当に42の学生かはAPIで検証する"""
        token = self._get_token()
        if not token: return False
        url = f"https://api.intra.42.fr/v2/users/{login.lower()}"
        return requests.get(url, headers={"Authorization": f"Bearer {token}"}).status_code == 200