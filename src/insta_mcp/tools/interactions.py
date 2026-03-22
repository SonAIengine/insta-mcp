"""Interaction tools - likes, comments, follows."""

from insta_mcp.server import mcp
from insta_mcp.client import client, rate_limit


# ─── Likes ────────────────────────────────────────────────────

@mcp.tool()
def like_post(media_url_or_code: str) -> dict:
    """Like an Instagram post.

    Args:
        media_url_or_code: Instagram post URL or shortcode
    """
    rate_limit("like")
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    result = cl.media_like(media_pk)
    return {"liked": result}


@mcp.tool()
def unlike_post(media_url_or_code: str) -> dict:
    """Unlike an Instagram post.

    Args:
        media_url_or_code: Instagram post URL or shortcode
    """
    rate_limit("like")
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    result = cl.media_unlike(media_pk)
    return {"unliked": result}


# ─── Comments ─────────────────────────────────────────────────

@mcp.tool()
def get_comments(media_url_or_code: str, amount: int = 20) -> list[dict]:
    """Get comments on a post.

    Args:
        media_url_or_code: Instagram post URL or shortcode
        amount: Number of comments to fetch (default 20, max 100)
    """
    rate_limit()
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    amount = min(amount, 100)
    comments = cl.media_comments(media_pk, amount=amount)
    return [
        {
            "comment_id": str(c.pk),
            "username": c.user.username,
            "text": c.text,
            "timestamp": str(c.created_at_utc),
            "like_count": c.like_count,
        }
        for c in comments
    ]


@mcp.tool()
def post_comment(media_url_or_code: str, text: str) -> dict:
    """Post a comment on a post.

    Args:
        media_url_or_code: Instagram post URL or shortcode
        text: Comment text
    """
    rate_limit("comment")
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    c = cl.media_comment(media_pk, text)
    return {
        "comment_id": str(c.pk),
        "text": c.text,
    }


@mcp.tool()
def reply_to_comment(media_url_or_code: str, comment_id: str, text: str) -> dict:
    """Reply to a specific comment.

    Args:
        media_url_or_code: Instagram post URL or shortcode
        comment_id: Comment ID to reply to
        text: Reply text
    """
    rate_limit("comment")
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    c = cl.media_comment(media_pk, text, replied_to_comment_id=int(comment_id))
    return {
        "comment_id": str(c.pk),
        "text": c.text,
    }


@mcp.tool()
def delete_comment(media_url_or_code: str, comment_id: str) -> dict:
    """Delete a comment from a post.

    Args:
        media_url_or_code: Instagram post URL or shortcode
        comment_id: Comment ID to delete
    """
    rate_limit("comment")
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    result = cl.comment_delete(media_pk, int(comment_id))
    return {"deleted": result}


# ─── Follow ───────────────────────────────────────────────────

@mcp.tool()
def follow_user(username: str) -> dict:
    """Follow a user.

    Args:
        username: Instagram username to follow
    """
    rate_limit("follow")
    cl = client()
    user_id = cl.user_id_from_username(username)
    result = cl.user_follow(user_id)
    return {"followed": result}


@mcp.tool()
def unfollow_user(username: str) -> dict:
    """Unfollow a user.

    Args:
        username: Instagram username to unfollow
    """
    rate_limit("follow")
    cl = client()
    user_id = cl.user_id_from_username(username)
    result = cl.user_unfollow(user_id)
    return {"unfollowed": result}
