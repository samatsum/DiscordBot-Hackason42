import os
import json
import requests
import time
from typing import Optional

class FTAPIClient:
    def __init__(self, uid: str, secret: str):
        self.uid = uid
        self.secret = secret
        self.token = None
        self.cache_file = "src/data/user_cache.json"
        self.cache = self._load_cache()

    def _load_cache(self) -> dict:
        """起動時にファイルを読み込む"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Cache Load Error: {e}")
        return {}

    def _save_cache(self):
        """キャッシュをJSONファイルに物理保存"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Cache Save Error: {e}")

    def _get_token(self):
        """OAuth2 トークンを取得"""
        url = "https://api.intra.42.fr/oauth/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.uid,
            "client_secret": self.secret,
        }
        try:
            response = requests.post(url, data=data, timeout=5)
            if response.status_code == 200:
                self.token = response.json().get("access_token")
            else:
                print(f"Token Error: {response.status_code}")
        except Exception as e:
            print(f"Token Request Exception: {e}")

    def sync_all_tokyo_users(self):
        """一括取得。キャッシュが既に存在する場合はスキップする。"""
        
        # --- 【追加】これがないと、毎回ダウンロードし直してしまいます ---
        if self.cache:
            print(f"Cache found ({len(self.cache)} users). Skipping bulk sync.")
            return
        # -----------------------------------------------------------

        print("Starting bulk sync of 42Tokyo students...")
        if not self.token:
            self._get_token()

        if not self.token:
            print("Failed to get token. Aborting sync.")
            return

        page = 1
        while True:
            # ページごとにリクエスト
            url = f"https://api.intra.42.fr/v2/campus/26/users?page[size]=100&page[number]={page}"
            headers = {"Authorization": f"Bearer {self.token}"}
            
            try:
                # 2 req/s 制限を守るため、リクエスト前に必ず1秒待機
                time.sleep(1.5)
                
                response = requests.get(url, headers=headers, timeout=20)
                if response.status_code != 200:
                    print(f"Sync error at page {page}: {response.status_code}")
                    break
                
                users = response.json()
                if not users: # 中身が空になったら終了
                    break
                
                for u in users:
                    login = u.get("login")
                    img_url = u.get("image", {}).get("link")
                    if login and img_url:
                        self.cache[login] = img_url
                
                print(f"Page {page} synced ({len(users)} users)")
                page += 1
                
            except Exception as e:
                print(f"Sync critical error: {e}")
                break
        
        # 全件取得が終わったら一気に保存
        self._save_cache()
        print(f"Bulk sync completed. Total users cached: {len(self.cache)}")

    def get_user_image(self, login: str) -> Optional[str]:
        """画像URLを取得。一括取得済みなら一瞬で返る"""
        return self.cache.get(login)

    def validate_user(self, display_name: str) -> bool:
        """表示名がキャッシュ内に存在するか（42Tokyo生か）をチェック"""
        return display_name in self.cache