"""
max/plugins/mcp_manager.py

Manages the lifecycle of MCP server connections using langchain-mcp-adapters.
Wraps each MCP tool call with OTel spans tagged with max.run_id.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from max.otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("max.plugins.mcp_manager")

# Base directory for mcp/ plugin folders
MCP_DIR = Path(os.getenv("MCP_DIR", "./max/mcp"))


class MCPManager:
    """
    Manages MultiServerMCPClient lifecycle for all enabled MCP plugins.

    Usage:
        await mcp_manager.start()   # on app startup
        tools = mcp_manager.get_tools()
        await mcp_manager.stop()    # on app shutdown
    """

    def __init__(self, mcp_dir: Path = MCP_DIR):
        self.mcp_dir = mcp_dir
        self._client: Optional[Any] = None
        self._tools: list[Any] = []
        self._tool_map: dict[str, Any] = {}
        self._configs: dict[str, dict] = {}

    def _scan_configs(self) -> dict[str, dict]:
        """
        Scan mcp/ subdirectories for mcp.json files and build
        a config dict for MultiServerMCPClient.
        """
        import json

        configs: dict[str, dict] = {}
        if not self.mcp_dir.exists():
            logger.debug(f"[MCPManager] mcp/ dir not found at {self.mcp_dir}, skipping")
            return configs

        for folder in sorted(self.mcp_dir.iterdir()):
            manifest_path = folder / "mcp.json"
            if not folder.is_dir() or not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
                if not manifest.get("enabled", True):
                    logger.info(f"[MCPManager] Skipping disabled MCP server: {manifest.get('id')}")
                    continue

                server_id = manifest["id"]
                transport = manifest.get("transport", "stdio")

                if transport == "stdio":
                    # Resolve server.py path relative to the manifest folder
                    args = manifest.get("args", [])
                    if args and args[0].endswith(".py"):
                        server_script = str(folder / args[0])
                        args = [server_script] + args[1:]

                    configs[server_id] = {
                        "command": manifest["command"],
                        "args": args,
                        "env": {**os.environ, **manifest.get("env", {})},
                        "transport": "stdio",
                    }
                elif transport in ("http", "sse"):
                    configs[server_id] = {
                        "url": manifest["url"],
                        "transport": transport,
                    }
                else:
                    logger.warning(f"[MCPManager] Unknown transport '{transport}' for {server_id}")

            except Exception:
                logger.exception(f"[MCPManager] Failed to load MCP manifest: {manifest_path}")

        return configs

    async def start(self) -> None:
        """Connect to all enabled MCP servers and load their tools."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError:
            logger.warning(
                "[MCPManager] langchain-mcp-adapters not installed. "
                "MCP plugins will be unavailable. "
                "Install with: pip install langchain-mcp-adapters"
            )
            return

        self._configs = self._scan_configs()
        if not self._configs:
            logger.info("[MCPManager] No enabled MCP servers found.")
            return

        try:
            logger.info(f"[MCPManager] Connecting to {len(self._configs)} MCP server(s): {list(self._configs.keys())}")
            self._client = MultiServerMCPClient(self._configs)
            await self._client.__aenter__()
            self._tools = self._client.get_tools()
            self._tool_map = {tool.name: tool for tool in self._tools}
            logger.info(f"[MCPManager] Loaded {len(self._tools)} MCP tool(s): {list(self._tool_map.keys())}")
        except Exception:
            logger.exception("[MCPManager] Failed to start MCP client")
            self._client = None
            self._tools = []
            self._tool_map = {}

    async def stop(self) -> None:
        """Gracefully close all MCP server connections."""
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info("[MCPManager] MCP client stopped.")
            except Exception:
                logger.exception("[MCPManager] Error stopping MCP client")
            finally:
                self._client = None
                self._tools = []
                self._tool_map = {}

    async def reload(self) -> None:
        """Stop existing connections and reconnect with fresh config scan."""
        logger.info("[MCPManager] Reloading MCP servers...")
        await self.stop()
        await self.start()

    def get_tools(self) -> list[Any]:
        """Return all loaded LangChain tool objects from MCP servers."""
        return self._tools

    def get_tool_map(self) -> dict[str, Any]:
        """Return {tool_name: tool} for executor dispatch."""
        return self._tool_map

    def is_ready(self) -> bool:
        return self._client is not None

    async def invoke_tool(self, tool_name: str, message: str, run_id: str) -> str:
        """
        Invoke a named MCP tool with OTel instrumentation.
        Used by the executor when dispatching to an MCP plugin.
        """
        tool = self._tool_map.get(tool_name)
        if not tool:
            return f"Error: MCP tool '{tool_name}' not found. Available: {list(self._tool_map.keys())}"

        with tracer.start_as_current_span(f"mcp.tool.{tool_name}") as span:
            span.set_attribute("max.run_id", run_id)
            span.set_attribute("max.agent", f"mcp:{tool_name}")
            span.set_attribute("max.step", f"Invoking MCP tool: {tool_name}")
            span.set_attribute("max.mcp_tool", tool_name)

            try:
                result = await tool.ainvoke({"query": message})
                result_str = str(result)
                span.set_attribute("max.result_preview", result_str[:200])
                return result_str
            except Exception as e:
                logger.exception(f"[MCPManager] Error invoking tool '{tool_name}'")
                span.set_attribute("max.error", str(e))
                return f"Error invoking MCP tool '{tool_name}': {e}"


# Singleton — imported by registry and main.py
mcp_manager = MCPManager()
