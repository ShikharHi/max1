"""
max/api/plugins.py — Plugin discovery and toggle endpoints.
"""

from fastapi import APIRouter, HTTPException

from max.api.models import PluginToggleRequest, PluginResponse
from max.plugins import registry

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("", response_model=list[PluginResponse])
def list_plugins():
    return [PluginResponse(**p) for p in registry.get_all()]


@router.get("/{plugin_id}", response_model=PluginResponse)
def get_plugin(plugin_id: str):
    p = registry.get(plugin_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return PluginResponse(**p)


@router.patch("/{plugin_id}/toggle", response_model=PluginResponse)
def toggle_plugin(plugin_id: str, req: PluginToggleRequest):
    p = registry.toggle(plugin_id, req.enabled)
    if not p:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return PluginResponse(**p)
