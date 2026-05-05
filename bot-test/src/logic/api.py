import time
import requests

class FTAPIClient:
    def __init__(self, uid, secret):
        self.uid = uid
        self.secret = secret
        self.token = None
        self.expire_time = 0

    def _fetch_token(self):
        url = "https://api.intra.42.fr/oauth/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.uid,
            "client_secret": self.secret
        }
        res = requests.post(url, data=data)
        if res.status_code != 200:
            return False
        res_data = res.json()
        self.token = res_data["access_token"]
        self.expire_time = time.time() + res_data["expires_in"]
        return True

    def _get_token(self):
        if not self.token or time.time() >= self.expire_time:
            self._fetch_token()
        return self.token

    def validate_user(self, login):
        token = self._get_token()
        if not token:
            return False
        url = f"https://api.intra.42.fr/v2/users/{login}"
        res = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        return res.status_code == 200

    def search_users(self, prefix):
        token = self._get_token()
        if not token or not prefix:
            return []
        # Intra APIで検索
        url = f"https://api.intra.42.fr/v2/users?search[login]={prefix.lower()}"
        try:
            res = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=2.0)
            if res.status_code == 200:
                logins = [u['login'] for u in res.json()]
                # Python側で厳密に前方一致のみに絞り込む
                return [l for l in logins if l.startswith(prefix.lower())][:25]
        except:
            pass
        return []