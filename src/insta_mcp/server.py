"""FastMCP server definition."""

from fastmcp import FastMCP

mcp = FastMCP(
    "insta-mcp",
    instructions="Instagram automation MCP server. Manage posts, stories, reels, comments, DMs, and more.",
)

# Import tools to register them
import insta_mcp.tools.profile  # noqa: F401, E402
import insta_mcp.tools.media  # noqa: F401, E402
import insta_mcp.tools.publishing  # noqa: F401, E402
import insta_mcp.tools.interactions  # noqa: F401, E402
import insta_mcp.tools.messaging  # noqa: F401, E402
import insta_mcp.tools.feed  # noqa: F401, E402
