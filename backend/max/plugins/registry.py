"""
max/plugins/registry.py

Folder-based plugin/agent registry — extended with Claude-inspired
three-level lazy-loading for SKILL.md-based skills.

Scanning priority for skills/:
  1. SKILL.md  (new format — preferred)
  2. skill.json (legacy format — fallback)

Scanning for tools/, agents/, mcp/ is unchanged.

Three loading levels for SKILL.md skills
-----------------------------------------
Level 1 — Metadata  : always injected into the router system prompt
Level 2 — Body      : loaded by executor when the skill is selected
Level 3 — Resources : scripts/references/assets, loaded on demand

Public API
----------
  get_runner(plugin_id)          -> async callable(message, plan, run_id) -> str
  get_skill_manifest(plugin_id)  -> SkillManifest | None
  get_skill_body(plugin_id)      -> str | None
  get_skill_resources(plugin_id) -> dict[str, list[ResourceFile]] | None
  toggle(plugin_id, enabled)     -> persists to disk
  build_router_prompt()          -> str for router system prompt
  scan()                         -> re-discover all plugins (hot reload)
"""

import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from max.plugins.skill_loader import (
    ResourceFile,
    SkillManifest,
    list_skill_resources,
    load_manifest,
    load_skill_body,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory constants — overridable via environment variables
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent.parent  # → max/

SKILLS_DIR = Path(os.getenv("SKILLS_DIR", str(_HERE / "skills")))
TOOLS_DIR  = Path(os.getenv("TOOLS_DIR",  str(_HERE / "tools")))
AGENTS_DIR = Path(os.getenv("AGENTS_DIR", str(_HERE / "agents")))
MCP_DIR    = Path(os.getenv("MCP_DIR",    str(_HERE / "mcp")))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """
    Unified registry for skills, tools, agents, and MCP plugins.

    Skills with SKILL.md are loaded with the three-level system.
    Tools, agents, and MCP plugins continue to use their JSON manifests.
    """

    def __init__(self) -> None:
        # Core stores
        self._plugins:          dict[str, dict]          = {}  # id -> manifest dict
        self._runners:          dict[str, Callable]      = {}  # id -> async callable
        self._manifest_paths:   dict[str, Path]          = {}  # id -> path to manifest file

        # Level-1 skill manifests (SKILL.md only)
        self._skill_manifests:  dict[str, SkillManifest] = {}  # id -> SkillManifest
        # Tracks which plugin ids came from SKILL.md (vs legacy skill.json)
        self._skill_md_ids:     set[str]                 = set()

    # -----------------------------------------------------------------------
    # Scanning — hot reload safe
    # -----------------------------------------------------------------------

    def scan(self) -> None:
        """
        Scan all plugin directories and populate the registry.
        Safe to call multiple times (hot reload).
        """
        self._plugins.clear()
        self._runners.clear()
        self._manifest_paths.clear()
        self._skill_manifests.clear()
        self._skill_md_ids.clear()

        self._scan_skills_dir()
        self._scan_dir(TOOLS_DIR,  expected_type="tool",  manifest_name="tool.json")
        self._scan_agents_dir()
        self._scan_mcp_dir()

        logger.info(
            "[Registry] Discovered %d plugin(s): %s",
            len(self._plugins),
            list(self._plugins.keys()),
        )

    # ------------------------------------------------------------------
    # Skills directory — SKILL.md preferred, skill.json fallback
    # ------------------------------------------------------------------

    def _scan_skills_dir(self) -> None:
        """Scan skills/ preferring SKILL.md over legacy skill.json."""
        if not SKILLS_DIR.exists():
            return

        for folder in sorted(SKILLS_DIR.iterdir()):
            if not folder.is_dir():
                continue

            skill_md = folder / "SKILL.md"
            skill_json = folder / "skill.json"

            if skill_md.exists():
                self._load_skill_md(folder, skill_md)
            elif skill_json.exists():
                # Backward compat — legacy format
                self._load_plugin(skill_json, folder)
            else:
                logger.debug("[Registry] Skipping %s — no SKILL.md or skill.json", folder.name)

    def _load_skill_md(self, folder: Path, skill_md: Path) -> None:
        """
        Parse a SKILL.md skill — populate all three levels.

        Level 1 (metadata) is loaded eagerly.
        Level 2 (body) and Level 3 (resources) are loaded lazily by callers.
        """
        try:
            manifest = load_manifest(folder)
        except Exception:
            logger.exception("[Registry] Failed to parse SKILL.md in %s", folder)
            return

        plugin_id = manifest.id

        # Build a plain dict for the _plugins store so the rest of the API
        # (get_enabled, build_router_prompt, etc.) works uniformly.
        plugin_dict: dict[str, Any] = {
            "id":           manifest.id,
            "name":         manifest.name,
            "type":         "skill",
            "description":  manifest.description,
            "triggers":     manifest.triggers,
            "capabilities": manifest.capabilities,
            "enabled":      manifest.enabled,
            "entry_point":  manifest.entry_point,
            "function":     manifest.function,
            "_source":      "SKILL.md",  # internal marker
        }

        self._plugins[plugin_id]        = plugin_dict
        self._manifest_paths[plugin_id] = skill_md
        self._skill_manifests[plugin_id] = manifest
        self._skill_md_ids.add(plugin_id)

        logger.info("[Registry] Loaded skill manifest (SKILL.md) for '%s'", plugin_id)

        if not manifest.enabled:
            logger.debug("[Registry] Skill '%s' is disabled, skipping runner import", plugin_id)
            return

        if manifest.has_python_runner:
            module_path = folder / manifest.entry_point  # type: ignore[arg-type]
            if not module_path.exists():
                logger.error("[Registry] Entry point not found: %s", module_path)
                return
            runner = self._import_function(module_path, manifest.function, plugin_id)  # type: ignore[arg-type]
            if runner:
                self._runners[plugin_id] = self._ensure_async(runner)
                logger.info("[Registry] Loaded Python runner for skill '%s'", plugin_id)
        else:
            logger.info(
                "[Registry] Skill '%s' is LLM-guided (no Python runner). "
                "Executor will use the SKILL.md body as context.",
                plugin_id,
            )

    # ------------------------------------------------------------------
    # Generic directory scanners (tools, legacy skills, agents)
    # ------------------------------------------------------------------

    def _scan_dir(self, base_dir: Path, expected_type: str, manifest_name: str) -> None:
        """Generic scanner for tools/ (and legacy skill.json fallbacks)."""
        if not base_dir.exists():
            return
        for folder in sorted(base_dir.iterdir()):
            manifest_path = folder / manifest_name
            if not folder.is_dir() or not manifest_path.exists():
                continue
            self._load_plugin(manifest_path, folder)

    def _scan_agents_dir(self) -> None:
        """
        Scan agents/ directory.
        Only subdirectories with agent.json are treated as modular agents.
        Flat files (router.py, executor.py, etc.) are skipped.
        """
        if not AGENTS_DIR.exists():
            return
        for folder in sorted(AGENTS_DIR.iterdir()):
            manifest_path = folder / "agent.json"
            if not folder.is_dir() or not manifest_path.exists():
                continue
            self._load_plugin(manifest_path, folder)

    def _scan_mcp_dir(self) -> None:
        """
        Scan mcp/ directory.
        MCP plugins don't have Python entry points — dispatched via MCPManager.
        We still register them so the router can see them.
        """
        if not MCP_DIR.exists():
            return
        for folder in sorted(MCP_DIR.iterdir()):
            manifest_path = folder / "mcp.json"
            if not folder.is_dir() or not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugin_id = manifest["id"]
                manifest.setdefault("enabled", True)
                manifest.setdefault("capabilities", [])
                self._plugins[plugin_id]        = manifest
                self._manifest_paths[plugin_id] = manifest_path
            except Exception:
                logger.exception("[Registry] Failed to load MCP manifest: %s", manifest_path)

    def _load_plugin(self, manifest_path: Path, folder: Path) -> None:
        """Load a single plugin from a JSON manifest and import its module."""
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            plugin_id = manifest["id"]
            manifest.setdefault("enabled", True)
            manifest.setdefault("capabilities", [])

            self._plugins[plugin_id]        = manifest
            self._manifest_paths[plugin_id] = manifest_path

            if not manifest.get("enabled", True):
                logger.debug("[Registry] Plugin '%s' is disabled, skipping import", plugin_id)
                return

            entry_point   = manifest.get("entry_point")
            function_name = manifest.get("function")
            if not entry_point or not function_name:
                logger.warning(
                    "[Registry] Plugin '%s' missing entry_point/function in manifest", plugin_id
                )
                return

            module_path = folder / entry_point
            if not module_path.exists():
                logger.error("[Registry] Entry point not found: %s", module_path)
                return

            runner = self._import_function(module_path, function_name, plugin_id)
            if runner:
                self._runners[plugin_id] = self._ensure_async(runner)
                logger.info("[Registry] Loaded runner for '%s'", plugin_id)

        except Exception:
            logger.exception("[Registry] Failed to load plugin from: %s", manifest_path)

    # -----------------------------------------------------------------------
    # Dynamic import helpers
    # -----------------------------------------------------------------------

    def _import_function(
        self, module_path: Path, function_name: str, plugin_id: str
    ) -> Optional[Callable]:
        """Dynamically import a function from a module file."""
        try:
            module_name = f"max._plugins.{plugin_id}"
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                logger.error("[Registry] Cannot create module spec for %s", module_path)
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]

            fn = getattr(module, function_name, None)
            if fn is None:
                logger.error(
                    "[Registry] Function '%s' not found in %s", function_name, module_path
                )
                return None
            return fn
        except Exception:
            logger.exception("[Registry] Error importing %s::%s", module_path, function_name)
            return None

    @staticmethod
    def _ensure_async(fn: Callable) -> Callable:
        """Wrap a sync function so it can be awaited uniformly."""
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(fn):
            return fn

        async def _wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

        return _wrapper

    # -----------------------------------------------------------------------
    # MCP runner registration (called by main.py after mcp_manager.start())
    # -----------------------------------------------------------------------

    def register_mcp_runner(self, plugin_id: str, runner: Callable) -> None:
        """Register an async runner for an MCP plugin."""
        self._runners[plugin_id] = runner
        logger.info("[Registry] Registered MCP runner for '%s'", plugin_id)

    # -----------------------------------------------------------------------
    # Three-level skill API
    # -----------------------------------------------------------------------

    def get_skill_manifest(self, plugin_id: str) -> Optional[SkillManifest]:
        """Level-1: Return the SkillManifest for a SKILL.md skill, or None."""
        return self._skill_manifests.get(plugin_id)

    def get_skill_body(self, plugin_id: str) -> Optional[str]:
        """
        Level-2: Return the full SKILL.md instruction body for a skill.

        Returns None if the skill is not a SKILL.md skill.
        Returns an empty string if the body section is blank.
        """
        manifest = self._skill_manifests.get(plugin_id)
        if manifest is None or manifest.skill_md_path is None:
            return None
        return load_skill_body(manifest.skill_md_path.parent)

    def get_skill_resources(self, plugin_id: str) -> Optional[dict[str, list[ResourceFile]]]:
        """Level-3: Return the bundled resources for a skill, or None."""
        manifest = self._skill_manifests.get(plugin_id)
        if manifest is None or manifest.skill_md_path is None:
            return None
        return list_skill_resources(manifest.skill_md_path.parent)

    # -----------------------------------------------------------------------
    # General public API
    # -----------------------------------------------------------------------

    def get_runner(self, plugin_id: str) -> Optional[Callable]:
        """Return the async runner for a plugin, or None if not found/disabled."""
        plugin = self._plugins.get(plugin_id)
        if plugin and not plugin.get("enabled", True):
            return None
        return self._runners.get(plugin_id)

    def get_all(self) -> list[dict]:
        return list(self._plugins.values())

    def get_enabled(self) -> list[dict]:
        return [p for p in self._plugins.values() if p.get("enabled", True)]

    def get(self, plugin_id: str) -> Optional[dict]:
        return self._plugins.get(plugin_id)

    def toggle(self, plugin_id: str, enabled: bool) -> Optional[dict]:
        """Enable or disable a plugin — persists to its manifest file."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return None
        plugin["enabled"] = enabled

        # Also update the SkillManifest object if this is a SKILL.md skill
        if plugin_id in self._skill_manifests:
            self._skill_manifests[plugin_id].enabled = enabled

        # Update runner cache
        if not enabled:
            self._runners.pop(plugin_id, None)
        else:
            # Re-load runner if it was previously disabled
            manifest_path = self._manifest_paths.get(plugin_id)
            if manifest_path and plugin.get("type") != "mcp":
                folder = manifest_path.parent
                if plugin_id in self._skill_md_ids:
                    self._load_skill_md(folder, manifest_path)
                else:
                    self._load_plugin(manifest_path, folder)

        self._save(plugin_id)
        return plugin

    def _save(self, plugin_id: str) -> None:
        """Persist the in-memory manifest back to disk."""
        path = self._manifest_paths.get(plugin_id)
        if not path:
            return

        if plugin_id in self._skill_md_ids:
            # Update only the `enabled` field inside the SKILL.md frontmatter
            _update_skill_md_enabled(path, self._plugins[plugin_id].get("enabled", True))
        else:
            path.write_text(
                json.dumps(self._plugins[plugin_id], indent=2),
                encoding="utf-8",
            )

    # -----------------------------------------------------------------------
    # Router prompt builder
    # -----------------------------------------------------------------------

    def build_router_prompt(self) -> str:
        """Build the dynamic section of the router's system prompt."""
        enabled = self.get_enabled()
        if not enabled:
            return "No plugins are currently enabled. Handle all requests directly."

        skills  = [p for p in enabled if p.get("type") == "skill"]
        tools   = [p for p in enabled if p.get("type") == "tool"]
        agents  = [p for p in enabled if p.get("type") == "agent"]
        mcps    = [p for p in enabled if p.get("type") == "mcp"]

        lines: list[str] = []

        if skills:
            lines.append("## Skills\n")
            for p in skills:
                cap_str = ", ".join(p.get("capabilities", []))
                trigger_str = ""
                triggers = p.get("triggers", [])
                if triggers:
                    examples = ", ".join(f'"{t}"' for t in triggers[:5])
                    trigger_str = f" | triggers: {examples}"
                lines.append(
                    f"- **{p['id']}** (skill): {p['description'].strip()} "
                    f"[capabilities: {cap_str}{trigger_str}]"
                )

        if tools:
            lines.append("\n## Tools\n")
            for p in tools:
                cap_str = ", ".join(p.get("capabilities", []))
                lines.append(
                    f"- **{p['id']}** (tool): {p['description']} [capabilities: {cap_str}]"
                )

        if agents:
            lines.append("\n## Agents\n")
            for p in agents:
                cap_str = ", ".join(p.get("capabilities", []))
                lines.append(
                    f"- **{p['id']}** (agent): {p['description']} [capabilities: {cap_str}]"
                )

        if mcps:
            lines.append("\n## MCP Servers\n")
            for p in mcps:
                cap_str = ", ".join(p.get("capabilities", []))
                lines.append(
                    f"- **{p['id']}** (mcp): {p['description']} [capabilities: {cap_str}]"
                )

        lines.append(
            "\nRoute to the most appropriate agent/tool based on the user's intent. "
            "If no plugin fits, handle directly. Respond ONLY with JSON:\n"
            '{"intent": "<brief intent>", "selected_agent": "<plugin_id or \'direct\'>", '
            '"plan": "<one sentence plan>"}'
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper — update `enabled` inside SKILL.md frontmatter
# ---------------------------------------------------------------------------

_ENABLED_RE = re.compile(r"(^enabled\s*:\s*).*$", re.MULTILINE)


def _update_skill_md_enabled(skill_md_path: Path, enabled: bool) -> None:
    """
    Rewrite only the `enabled:` field in a SKILL.md frontmatter block.
    Leaves the rest of the file untouched.
    """
    try:
        text = skill_md_path.read_text(encoding="utf-8")
        new_value = "true" if enabled else "false"

        def _replacer(m: re.Match) -> str:
            return f"{m.group(1)}{new_value}"

        new_text = _ENABLED_RE.sub(_replacer, text, count=1)
        skill_md_path.write_text(new_text, encoding="utf-8")
    except OSError:
        logger.warning("[Registry] Could not persist enabled state to %s", skill_md_path)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

registry = PluginRegistry()
