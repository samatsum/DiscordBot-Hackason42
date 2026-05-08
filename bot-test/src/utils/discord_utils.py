import discord
from logic.models import MatchRequest

DETAIL_EMOJI_MAP = {
    "meal": "🍽️", "game": "🎮", "exercise": "🏃",
}

async def send_match_dm(user: discord.User, opponent_intra: str, image_url: str):
    """マッチング成立時のDM通知"""
    embed = discord.Embed(title="🎉 マッチング成立！", description=f"**{opponent_intra}** さんとマッチング！", color=0x00ff00)
    if image_url:
        embed.set_image(url=image_url)
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass # DM閉鎖ユーザーへの対応

async def post_to_matching_channel(guild: discord.Guild, req: MatchRequest) -> bool:
    """募集をチャンネルに投稿する"""
    channel = discord.utils.get(guild.text_channels, name=f"matching_{req.detail}")
    if not channel:
        return False

    embed = discord.Embed(title=f"{DETAIL_EMOJI_MAP[req.detail]} マッチング募集", color=0x3498db)
    embed.add_field(name="👤 ユーザー", value=req.intra_name, inline=True)
    embed.add_field(name="🕐 時間", value=f"{req.start_time.strftime('%H:%M')} - {req.end_time.strftime('%H:%M')}")
    
    msg = await channel.send(embed=embed)
    req.message_id = msg.id
    return True