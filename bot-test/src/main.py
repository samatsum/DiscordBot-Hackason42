import discord
import os
from dotenv import load_dotenv

load_dotenv()

class MyClient(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}!')

    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.content == 'ping':
            await message.channel.send('pong')

# --- ここを修正 ---
intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を読み取る権限を有効化
client = MyClient(intents=intents)
# ------------------

client.run(os.getenv('DISCORD_TOKEN'))