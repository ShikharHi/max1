"""
max/api/plugins.py — Plugin discovery, toggle, and reload endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException

from max.api.models import PluginToggleRequest, PluginResponse
from max.plugins import registry, mcp_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("", response_model=list[PluginResponse])
def list_plugins():
    """List all discovered plugins (skills + tools + agents + mcp)."""
    return [PluginResponse(**_to_response(p)) for p in registry.get_all()]


@router.get("/{plugin_id}", response_model=PluginResponse)
def get_plugin(plugin_id: str):
    """Get details for a specific plugin by ID."""
    p = registry.get(plugin_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return PluginResponse(**_to_response(p))


@router.patch("/{plugin_id}/toggle", response_model=PluginResponse)
async def toggle_plugin(plugin_id: str, req: PluginToggleRequest):
    """Enable or disable a plugin. Persists to its JSON manifest on disk."""
    p = registry.toggle(plugin_id, req.enabled)
    if not p:
        raise HTTPException(status_code=404, detail="Plugin not found")

    # If the toggled plugin is an MCP type, reload MCP connections
    if p.get("type") == "mcp":
        logger.info(f"[Plugins API] MCP plugin '{plugin_id}' toggled — reloading MCP manager")
        await mcp_manager.reload()
        _register_mcp_runners()

    return PluginResponse(**_to_response(p))


@router.post("/reload")
async def reload_plugins():
    """
    Hot-reload all plugins: re-scan directories and reconnect MCP servers.
    Use this after adding a new plugin folder without restarting the server.
    """
    logger.info("[Plugins API] Hot-reloading all plugins...")
    registry.scan()

    # Restart MCP connections with fresh config
    await mcp_manager.reload()
    _register_mcp_runners()

    return {
        "status": "ok",
        "plugins": len(registry.get_all()),
        "enabled": len(registry.get_enabled()),
        "mcp_tools": len(mcp_manager.get_tools()),
    }


def _to_response(manifest: dict) -> dict:
    """Normalize a manifest dict to match PluginResponse fields."""
    return {
        "id": manifest.get("id", ""),
        "name": manifest.get("name", ""),
        "type": manifest.get("type", "unknown"),
        "description": manifest.get("description", ""),
        "enabled": manifest.get("enabled", True),
        "capabilities": manifest.get("capabilities", []),
        "framework": manifest.get("framework", "any"),
    }


def _register_mcp_runners() -> None:
    """Wire MCP tool runners into the registry after mcp_manager starts."""
    tool_map = mcp_manager.get_tool_map()
    for plugin_id, manifest in {
        pid: m for pid, m in {p["id"]: p for p in registry.get_all()}.items()
        if m.get("type") == "mcp"
    }.items():
        if not manifest.get("enabled", True):
            continue
        # Build a runner that dispatches to the best matching MCP tool
        # by iterating capabilities and finding the first matching tool
        capabilities = manifest.get("capabilities", [])
        matched_tools = [tool_map[cap] for cap in capabilities if cap in tool_map]

        if matched_tools:
            # Use first capability as primary tool; LLM will handle the rest
            primary_tool = matched_tools[0]

            async def _runner(msg: str, plan: str, rid: str, _tool=primary_tool, _sid=plugin_id) -> str:
                return await mcp_manager.invoke_tool(_tool.name, msg, rid)

            registry.register_mcp_runner(plugin_id, _runner)
        else:
            # Generic runner: let mcp_manager find tool by server id
            async def _generic_runner(msg: str, plan: str, rid: str, _sid=plugin_id) -> str:
                # Try each tool from this MCP server's capabilities
                caps = registry.get(plugin_id).get("capabilities", [])
                for cap in caps:
                    if cap in mcp_manager.get_tool_map():
                        return await mcp_manager.invoke_tool(cap, msg, rid)
                return f"No available MCP tools for '{_sid}'. Tools loaded: {list(mcp_manager.get_tool_map().keys())}"

            registry.register_mcp_runner(plugin_id, _generic_runner)
