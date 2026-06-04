from __future__ import annotations

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("isotope-test-echo")


@mcp.tool()
def echo(text: str) -> dict[str, str]:
    """Echo text for Isotope MCP client tests."""
    return {"echo": text}


@mcp.tool()
def fail(message: str) -> dict[str, str]:
    """Raise a predictable tool-level error."""
    raise ValueError(message)


if __name__ == "__main__":
    mcp.run()
