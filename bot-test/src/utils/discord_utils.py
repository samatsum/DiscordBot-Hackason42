import discord
from logic.models import MatchRequest
from datetime import datetime, timedelta

DETAIL_EMOJI_MAP = {
    "meal": "🍽️", "game": "🎮", "exercise": "🏃",
}

async def send_match_dm(user: discord.User, opponent_intra: str, image_url: str, start_time: datetime, end_time: datetime, detail: str):
    """マッチング成立時のDM通知（詳細情報追加版）"""
    emoji = DETAIL_EMOJI_MAP.get(detail, "")
    time_str = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    
    embed = discord.Embed(
        title="🎉 マッチング成立！", 
        description=f"**{opponent_intra}** さんとマッチングしました！", 
        color=0x00ff00
    )
    # 詳細情報の追加
    embed.add_field(name=f"{emoji} 目的", value=detail, inline=True)
    embed.add_field(name="🕐 時間帯", value=time_str, inline=True)
    
    if image_url:
        embed.set_image(url=image_url)
        
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass

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

async def delete_channel_message(guild: discord.Guild, req: MatchRequest):
    """チャンネルに投稿されたマッチング情報を削除する"""
    if not req.message_id:
        return

    channel = discord.utils.get(guild.text_channels, name=f"matching_{req.detail}")
    if not channel:
        return

    try:
        msg = await channel.fetch_message(req.message_id)
        await msg.delete()
    except (discord.NotFound, discord.HTTPException):
        pass

async def announce_match(guild: discord.Guild, my_req: MatchRequest, opp_req: MatchRequest):
    """
    チャンネル上でメンションを飛ばし、マッチング成立を公表する。
    """
    channel = discord.utils.get(guild.text_channels, name=f"matching_{my_req.detail}")
    if not channel:
        return

    # メンション文字列の作成 (<@ID> の形式)
    m_1 = f"<@{my_req.discord_id}>"
    m_2 = f"<@{opp_req.discord_id}>"
    
    embed = discord.Embed(
        title="🤝 マッチング成立！",
        description=f"{m_1} さんと {m_2} さんのマッチングが成立しました！　DMを確認してください！",
        color=0x2ecc71 # 緑色
    )
    # チャンネルへ投稿（これにより両者に通知が行く）
    await channel.send(content=f"{m_1} {m_2}", embed=embed)