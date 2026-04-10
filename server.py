import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("octo-mcp-server", stateless_http=True)


@mcp.tool()
async def echo(message: str) -> str:
    """
    Returns the provided message unchanged. Useful for testing connectivity.

    Args:
        message: The message to echo back.
    """
    return message


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
