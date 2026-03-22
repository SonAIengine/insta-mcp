"""DM (Direct Message) tools."""

from insta_mcp.server import mcp
from insta_mcp.client import client, rate_limit


@mcp.tool()
def get_dm_threads(amount: int = 20) -> list[dict]:
    """Get recent DM conversation threads.

    Args:
        amount: Number of threads to fetch (default 20, max 50)
    """
    rate_limit("dm")
    cl = client()
    amount = min(amount, 50)
    threads = cl.direct_threads(amount=amount)
    return [
        {
            "thread_id": str(t.id),
            "users": [u.username for u in t.users],
            "last_message": t.messages[0].text if t.messages else None,
            "last_timestamp": str(t.messages[0].timestamp) if t.messages else None,
        }
        for t in threads
    ]


@mcp.tool()
def get_dm_messages(thread_id: str, amount: int = 20) -> list[dict]:
    """Get messages from a specific DM thread.

    Args:
        thread_id: DM thread ID
        amount: Number of messages to fetch (default 20, max 50)
    """
    rate_limit("dm")
    cl = client()
    amount = min(amount, 50)
    thread = cl.direct_thread(thread_id, amount=amount)
    return [
        {
            "message_id": str(msg.id),
            "user_id": str(msg.user_id),
            "text": msg.text,
            "timestamp": str(msg.timestamp),
            "item_type": msg.item_type,
        }
        for msg in thread.messages
    ]


@mcp.tool()
def send_dm(username: str, text: str) -> dict:
    """Send a direct message to a user.

    Args:
        username: Instagram username to send DM to
        text: Message text
    """
    rate_limit("dm")
    cl = client()
    user_id = cl.user_id_from_username(username)
    thread = cl.direct_send(text, user_ids=[int(user_id)])
    return {
        "thread_id": str(thread.id) if thread else None,
        "sent": True,
    }


@mcp.tool()
def send_dm_to_thread(thread_id: str, text: str) -> dict:
    """Send a message to an existing DM thread.

    Args:
        thread_id: DM thread ID
        text: Message text
    """
    rate_limit("dm")
    cl = client()
    result = cl.direct_answer(thread_id, text)
    return {
        "thread_id": thread_id,
        "sent": bool(result),
    }
