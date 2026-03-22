"""Media tools - fetch posts, reels, stories."""

from insta_mcp.server import mcp
from insta_mcp.client import client


def _media_to_dict(m) -> dict:
    return {
        "media_id": str(m.pk),
        "code": m.code,
        "media_type": str(m.media_type),
        "caption": m.caption_text if hasattr(m, "caption_text") else str(m.caption_text) if m.caption_text else "",
        "like_count": m.like_count,
        "comment_count": m.comment_count,
        "timestamp": str(m.taken_at),
        "url": f"https://www.instagram.com/p/{m.code}/",
        "thumbnail_url": str(m.thumbnail_url) if m.thumbnail_url else None,
    }


@mcp.tool()
def get_user_posts(username: str, amount: int = 12) -> list[dict]:
    """Get recent posts from a user's profile.

    Args:
        username: Instagram username
        amount: Number of posts to fetch (default 12, max 50)
    """
    cl = client()
    user_id = cl.user_id_from_username(username)
    amount = min(amount, 50)
    medias = cl.user_medias(user_id, amount=amount)
    return [_media_to_dict(m) for m in medias]


@mcp.tool()
def get_media_info(media_url_or_code: str) -> dict:
    """Get detailed info about a specific post by URL or shortcode.

    Args:
        media_url_or_code: Instagram post URL (https://www.instagram.com/p/XXX/) or shortcode
    """
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    m = cl.media_info(media_pk)
    return _media_to_dict(m)


@mcp.tool()
def get_user_stories(username: str) -> list[dict]:
    """Get current stories from a user.

    Args:
        username: Instagram username
    """
    cl = client()
    user_id = cl.user_id_from_username(username)
    stories = cl.user_stories(user_id)
    return [
        {
            "story_id": str(s.pk),
            "media_type": str(s.media_type),
            "timestamp": str(s.taken_at),
            "url": str(s.thumbnail_url) if s.thumbnail_url else None,
            "video_url": str(s.video_url) if s.video_url else None,
        }
        for s in stories
    ]


@mcp.tool()
def get_user_reels(username: str, amount: int = 12) -> list[dict]:
    """Get recent reels from a user.

    Args:
        username: Instagram username
        amount: Number of reels to fetch (default 12, max 50)
    """
    cl = client()
    user_id = cl.user_id_from_username(username)
    amount = min(amount, 50)
    reels = cl.user_clips(user_id, amount=amount)
    return [_media_to_dict(m) for m in reels]
