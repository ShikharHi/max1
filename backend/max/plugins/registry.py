"""
max/plugins/registry.py

Manifest-driven plugin/agent registry.
Each plugin has a JSON manifest defining its capabilities.
Registry builds the router's system prompt dynamically.
Hot plug/unplug — enable/disable persists to manifests on disk.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path(os.getenv("PLUGINS_DIR", "./max/plugins/manifests"))


class PluginRegistry:
    def __init__(self, manifests_dir: Path = MANIFESTS_DIR):
        self.manifests_dir = manifests_dir
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, dict] = {}
        self._load_all()

    def _load_all(self) -> None:
        self._plugins.clear()
        for f in self.manifests_dir.glob("*.json"):
            try:
                manifest = json.loads(f.read_text())
                self._plugins[manifest["id"]] = manifest
            except Exception:
                logger.exception(f"Failed to load manifest: {f}")
        logger.info(f"[Registry] Loaded {len(self._plugins)} plugins")

    def get_all(self) -> list[dict]:
        return list(self._plugins.values())

    def get_enabled(self) -> list[dict]:
        return [p for p in self._plugins.values() if p.get("enabled", True)]

    def get(self, plugin_id: str) -> Optional[dict]:
        return self._plugins.get(plugin_id)

    def toggle(self, plugin_id: str, enabled: bool) -> Optional[dict]:
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return None
        plugin["enabled"] = enabled
        self._save(plugin)
        return plugin

    def _save(self, manifest: dict) -> None:
        path = self.manifests_dir / f"{manifest['id']}.json"
        path.write_text(json.dumps(manifest, indent=2))

    def build_router_prompt(self) -> str:
        """Build the dynamic section of the router's system prompt."""
        enabled = self.get_enabled()
        if not enabled:
            return "No plugins are currently enabled. Handle all requests directly."

        lines = ["Available agents and tools:\n"]
        for p in enabled:
            cap_str = ", ".join(p.get("capabilities", []))
            lines.append(
                f"- **{p['id']}** ({p['type']}): {p['description']} "
                f"[capabilities: {cap_str}]"
            )

        lines.append(
            "\nRoute to the most appropriate agent/tool based on the user's intent. "
            "If no plugin fits, handle directly. Respond ONLY with JSON:\n"
            '{"intent": "<brief intent>", "selected_agent": "<plugin_id or \'direct\'>", '
            '"plan": "<one sentence plan>"}'
        )
        return "\n".join(lines)


# Singleton
registry = PluginRegistry()
