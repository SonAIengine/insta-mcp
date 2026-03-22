"""Profile tools."""

from insta_mcp.server import mcp
from insta_mcp.client import client


@mcp.tool()
def get_my_profile() -> dict:
    """Get my Instagram profile info (followers, following, bio, etc)."""
    cl = client()
    info = cl.user_info(cl.user_id)
    return {
        "user_id": str(info.pk),
        "username": info.username,
        "full_name": info.full_name,
        "biography": info.biography,
        "follower_count": info.follower_count,
        "following_count": info.following_count,
        "media_count": info.media_count,
        "is_private": info.is_private,
        "is_verified": info.is_verified,
        "profile_pic_url": str(info.profile_pic_url),
    }


@mcp.tool()
def get_user_profile(username: str) -> dict:
    """Get another user's public profile info.

    Args:
        username: Instagram username (without @)
    """
    cl = client()
    info = cl.user_info_by_username(username)
    return {
        "user_id": str(info.pk),
        "username": info.username,
        "full_name": info.full_name,
        "biography": info.biography,
        "follower_count": info.follower_count,
        "following_count": info.following_count,
        "media_count": info.media_count,
        "is_private": info.is_private,
        "is_verified": info.is_verified,
        "profile_pic_url": str(info.profile_pic_url),
    }


@mcp.tool()
def get_followers(username: str, amount: int = 20) -> list[dict]:
    """Get a user's followers list.

    Args:
        username: Instagram username
        amount: Number of followers to fetch (default 20, max 100)
    """
    cl = client()
    user_id = cl.user_id_from_username(username)
    amount = min(amount, 100)
    followers = cl.user_followers(user_id, amount=amount)
    return [
        {"user_id": str(uid), "username": info.username, "full_name": info.full_name}
        for uid, info in followers.items()
    ]


@mcp.tool()
def get_following(username: str, amount: int = 20) -> list[dict]:
    """Get a user's following list.

    Args:
        username: Instagram username
        amount: Number of following to fetch (default 20, max 100)
    """
    cl = client()
    user_id = cl.user_id_from_username(username)
    amount = min(amount, 100)
    following = cl.user_following(user_id, amount=amount)
    return [
        {"user_id": str(uid), "username": info.username, "full_name": info.full_name}
        for uid, info in following.items()
    ]
