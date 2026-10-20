"""Account tools - list and switch Instagram accounts.

Registering accounts is CLI-only (python -m insta_mcp.accounts add <name>) so passwords never pass through chat.
"""

from insta_mcp.server import mcp
from insta_mcp.client import get_active_account, list_accounts as _list_accounts, set_active_account


@mcp.tool()
def list_accounts() -> dict:
    """List registered Instagram accounts and which one is active."""
    return {"active": get_active_account(), "accounts": _list_accounts()}


@mcp.tool()
def switch_account(name: str) -> dict:
    """Switch the Instagram account used by all other tools.

    Args:
        name: Account name from list_accounts ("default" is the original account)
    """
    set_active_account(name)
    return {"active": name}
