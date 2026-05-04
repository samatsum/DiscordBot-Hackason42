import discord
import os
import requests
from dotenv import load_dotenv

# .env ファイルから環境変数を読み込む
load_dotenv()

class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_base_url = "https://api.intra.42.fr/oauth/token"
        self.user_api_url = "https://api.intra.42.fr/v2/users/"

    async def on_ready(self):
        print(f'Logged on as {self.user}!')

    async def on_message(self, message):
        # ボット自身のメッセージには反応しない
        if message.author == self.user:
            return

        # 1. 既存の ping/pong 機能
        if message.content == 'ping':
            await message.channel.send('pong')

        # 2. Intra名確認機能 (!check [intra_id] という形式を想定)
        if message.content.startswith('!check '):
            intra_id = message.content.split(' ')[1]
            await self.check_42_user(message.channel, intra_id)

    async def get_42_token(self):
        """42 API のアクセストークンを取得する (Client Credentials Grant)"""
        uid = os.getenv('FORTYTWO_APP_UID')
        secret = os.getenv('FORTYTWO_APP_SECRET')
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": uid,
            "client_secret": secret
        }
        
        try:
            response = requests.post(self.api_base_url, data=payload)
            response.raise_for_status()
            return response.json().get("access_token")
        except Exception as e:
            print(f"Token Error: {e}")
            return None

    async def check_42_user(self, channel, intra_id):
        """指定された Intra 名の学生が存在するか確認する"""
        token = await self.get_42_token()
        if not token:
            await channel.send("APIトークンの取得に失敗しました。")
            return

        headers = {"Authorization": f"Bearer {token}"}
        try:
            # 指定されたIDのユーザー情報を取得
            res = requests.get(f"{self.user_api_url}{intra_id}", headers=headers)
            
            if res.status_code == 200:
                user_data = res.json()
                display_name = user_data.get('displayname', 'Unknown')
                location = user_data.get('location') or "Away"
                await channel.send(f"✅ 学生が見つかりました: **{display_name}** (現在: {location})")
            elif res.status_code == 404:
                await channel.send(f"❌ `{intra_id}` という学生は見つかりませんでした。")
            else:
                await channel.send(f"⚠️ APIエラーが発生しました (Status: {res.status_code})")
        except Exception as e:
            await channel.send(f"通信エラーが発生しました: {e}")

# Intents の設定 (Message Content を有効化)
intents = discord.Intents.default()
intents.message_content = True 

client = MyClient(intents=intents)
client.run(os.getenv('DISCORD_TOKEN'))