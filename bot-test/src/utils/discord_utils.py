import discord
from logic.models import MatchRequest, DETAIL_EMOJI_MAP
from datetime import datetime, timedelta


async def send_match_dm(user: discord.User, opponent_intra: str, image_url: str, 
                        start_time: datetime, end_time: datetime, detail: str):
    """マッチング成立時のDM通知"""
    emoji = DETAIL_EMOJI_MAP.get(detail, "❓")
    time_str = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    
    embed = discord.Embed(title="🎉 マッチング成立！", description=f"**{opponent_intra}** さんとマッチング！", color=0x00ff00)
    embed.add_field(name=f"{emoji} 目的", value=detail, inline=True)
    embed.add_field(name="🕐 時間帯", value=time_str, inline=True)
    
    if image_url:
        embed.set_image(url=image_url)
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass

async def post_to_matching_channel(guild: discord.Guild, req: MatchRequest) -> bool:
    """マッチング募集をチャンネルに投稿する"""
    channel = discord.utils.get(guild.text_channels, name=f"matching_{req.detail}")
    if not channel:
        return False

    # 【修正点】req.detail.emoji を DETAIL_EMOJI_MAP.get(req.detail, "❓") に変更
    emoji = DETAIL_EMOJI_MAP.get(req.detail, "❓")
    embed = discord.Embed(title=f"{emoji} マッチング募集", color=0x3498db)
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
    channel = discord.utils.get(guild.text_channels, name=f"matching_{my_req.detail}")
    if not channel: return

    # 代表者 + 同行者全員のメンションを作成
    def get_mentions(req):
        ids = [req.discord_id] + req.other_discord_ids
        return " ".join([f"<@{uid}>" for uid in ids])

    m_1, m_2 = get_mentions(my_req), get_mentions(opp_req)
    
    embed = discord.Embed(
        title="🤝 マッチング成立！",
        description=f"{m_1}\nと\n{m_2}\nのマッチングが成立しました！",
        color=0x2ecc71
    )
    await channel.send(content=f"{m_1} {m_2}", embed=embed)