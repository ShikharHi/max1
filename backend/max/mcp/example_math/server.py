"""
max/mcp/example_math/server.py

Example FastMCP server — simple arithmetic operations for testing MCP integration.

Run with:
    python server.py

Or via the mcp.json manifest (stdio transport).
"""

try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError(
        "fastmcp is required to run this MCP server. "
        "Install with: pip install fastmcp"
    )

mcp = FastMCP("Math Server")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers together."""
    return a * b


@mcp.tool()
def divide(a: float, b: float) -> float:
    """Divide a by b. Raises error if b is zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


@mcp.tool()
def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


if __name__ == "__main__":
    mcp.run()
