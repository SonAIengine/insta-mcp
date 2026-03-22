"""Publishing tools - post photos, videos, reels, stories."""

import tempfile
import urllib.request
from pathlib import Path

from insta_mcp.server import mcp
from insta_mcp.client import client, rate_limit


@mcp.tool()
def publish_photo(image_path: str, caption: str = "") -> dict:
    """Publish a photo post to Instagram.

    Args:
        image_path: Local file path to the image (JPEG/PNG)
        caption: Post caption (max 2200 chars)
    """
    rate_limit()
    cl = client()
    m = cl.photo_upload(Path(image_path), caption=caption)
    return {
        "media_id": str(m.pk),
        "code": m.code,
        "url": f"https://www.instagram.com/p/{m.code}/",
    }


@mcp.tool()
def publish_photo_from_url(image_url: str, caption: str = "") -> dict:
    """Download an image from URL and publish to Instagram.

    Args:
        image_url: HTTPS URL of the image
        caption: Post caption (max 2200 chars)
    """
    rate_limit()
    cl = client()
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        urllib.request.urlretrieve(image_url, f.name)
        m = cl.photo_upload(Path(f.name), caption=caption)
    return {
        "media_id": str(m.pk),
        "code": m.code,
        "url": f"https://www.instagram.com/p/{m.code}/",
    }


@mcp.tool()
def publish_video(video_path: str, caption: str = "", thumbnail_path: str = "") -> dict:
    """Publish a video post to Instagram feed.

    Args:
        video_path: Local file path to the video
        caption: Post caption
        thumbnail_path: Optional thumbnail image path
    """
    rate_limit()
    cl = client()
    kwargs = {"caption": caption}
    if thumbnail_path:
        kwargs["thumbnail"] = Path(thumbnail_path)
    m = cl.video_upload(Path(video_path), **kwargs)
    return {
        "media_id": str(m.pk),
        "code": m.code,
        "url": f"https://www.instagram.com/p/{m.code}/",
    }


@mcp.tool()
def publish_reel(video_path: str, caption: str = "", thumbnail_path: str = "") -> dict:
    """Publish a Reel (short video) to Instagram.

    Args:
        video_path: Local file path to the video
        caption: Reel caption
        thumbnail_path: Optional thumbnail image path
    """
    rate_limit()
    cl = client()
    kwargs = {"caption": caption}
    if thumbnail_path:
        kwargs["thumbnail"] = Path(thumbnail_path)
    m = cl.clip_upload(Path(video_path), **kwargs)
    return {
        "media_id": str(m.pk),
        "code": m.code,
        "url": f"https://www.instagram.com/p/{m.code}/",
    }


@mcp.tool()
def publish_story_photo(image_path: str) -> dict:
    """Publish a photo story (disappears after 24h).

    Args:
        image_path: Local file path to the image
    """
    rate_limit()
    cl = client()
    m = cl.photo_upload_to_story(Path(image_path))
    return {
        "story_id": str(m.pk),
    }


@mcp.tool()
def publish_story_video(video_path: str) -> dict:
    """Publish a video story (disappears after 24h).

    Args:
        video_path: Local file path to the video
    """
    rate_limit()
    cl = client()
    m = cl.video_upload_to_story(Path(video_path))
    return {
        "story_id": str(m.pk),
    }


@mcp.tool()
def publish_album(paths: list[str], caption: str = "") -> dict:
    """Publish a carousel/album post with multiple images or videos.

    Args:
        paths: List of local file paths (images and/or videos, 2-10 items)
        caption: Post caption
    """
    rate_limit()
    cl = client()
    media_paths = [Path(p) for p in paths]
    m = cl.album_upload(media_paths, caption=caption)
    return {
        "media_id": str(m.pk),
        "code": m.code,
        "url": f"https://www.instagram.com/p/{m.code}/",
    }


@mcp.tool()
def delete_media(media_url_or_code: str) -> dict:
    """Delete a post from Instagram.

    Args:
        media_url_or_code: Instagram post URL or shortcode
    """
    rate_limit()
    cl = client()
    if media_url_or_code.startswith("http"):
        media_pk = cl.media_pk_from_url(media_url_or_code)
    else:
        media_pk = cl.media_pk_from_code(media_url_or_code)
    result = cl.media_delete(media_pk)
    return {"deleted": result}
