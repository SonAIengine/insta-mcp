"""Feed and discovery tools."""

from insta_mcp.server import mcp
from insta_mcp.client import client


@mcp.tool()
def get_timeline(amount: int = 20) -> list[dict]:
    """Get posts from my home timeline/feed.

    Args:
        amount: Number of posts to fetch (default 20, max 50)
    """
    cl = client()
    amount = min(amount, 50)
    medias = cl.get_timeline_feed()["feed_items"][:amount]
    results = []
    for item in medias:
        m = item.get("media_or_ad")
        if not m:
            continue
        results.append({
            "media_id": m.get("pk"),
            "username": m.get("user", {}).get("username"),
            "caption": (m.get("caption") or {}).get("text", ""),
            "like_count": m.get("like_count", 0),
            "comment_count": m.get("comment_count", 0),
            "media_type": m.get("media_type"),
        })
    return results


@mcp.tool()
def search_hashtag(hashtag: str, amount: int = 20) -> list[dict]:
    """Search for top posts with a specific hashtag.

    Args:
        hashtag: Hashtag to search (without #)
        amount: Number of posts to fetch (default 20, max 50)
    """
    cl = client()
    amount = min(amount, 50)
    medias = cl.hashtag_medias_top(hashtag, amount=amount)
    return [
        {
            "media_id": str(m.pk),
            "code": m.code,
            "username": m.user.username if m.user else None,
            "caption": m.caption_text or "",
            "like_count": m.like_count,
            "comment_count": m.comment_count,
            "url": f"https://www.instagram.com/p/{m.code}/",
        }
        for m in medias
    ]


@mcp.tool()
def search_users(query: str) -> list[dict]:
    """Search for Instagram users by name or username.

    Args:
        query: Search query string
    """
    cl = client()
    users = cl.search_users(query)
    return [
        {
            "user_id": str(u.pk),
            "username": u.username,
            "full_name": u.full_name,
            "is_verified": u.is_verified,
            "follower_count": u.follower_count,
        }
        for u in users[:20]
    ]


@mcp.tool()
def search_location(query: str) -> list[dict]:
    """Search for Instagram locations/places.

    Args:
        query: Location search query
    """
    cl = client()
    locations = cl.search_places(query)
    return [
        {
            "location_id": str(loc.pk),
            "name": loc.name,
            "address": loc.address,
            "lat": loc.lat,
            "lng": loc.lng,
        }
        for loc in locations[:20]
    ]
