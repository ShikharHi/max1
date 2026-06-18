# Example Math MCP Server

A simple [FastMCP](https://github.com/jlowin/fastmcp) server that exposes basic arithmetic operations for testing MAX's MCP integration.

## Tools

| Tool | Description | Args |
|------|-------------|------|
| `add` | Add two numbers | `a: float, b: float` |
| `multiply` | Multiply two numbers | `a: float, b: float` |
| `divide` | Divide a by b | `a: float, b: float` |
| `subtract` | Subtract b from a | `a: float, b: float` |

## Transport

This server uses **stdio** transport (spawned as a subprocess by `langchain-mcp-adapters`).

## Running Manually

```bash
pip install fastmcp
python server.py
```

## Configuration (`mcp.json`)

```json
{
  "id": "math_server",
  "name": "Math MCP Server",
  "type": "mcp",
  "description": "Arithmetic operations via MCP.",
  "enabled": true,
  "capabilities": ["add", "multiply", "divide"],
  "transport": "stdio",
  "command": "python",
  "args": ["server.py"],
  "env": {}
}
```

## Testing via MAX

Once the server is running and registered, send a message like:
- "what is 3 + 5?"
- "multiply 12 by 7"
- "divide 100 by 4"

The router will route to `math_server` and the MCP tool will be invoked.
