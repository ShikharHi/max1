"""
max/plugins/skill_loader.py

Three-level lazy-loading machinery for SKILL.md-based skills.

Level 1 — Metadata (always present in router prompt):
    Parsed from YAML frontmatter in SKILL.md.

Level 2 — Body (loaded when skill is selected):
    Full markdown instruction body from SKILL.md (everything after frontmatter).

Level 3 — Resources (loaded on demand):
    Scripts / references / assets bundled under resources/ in the skill folder.

Public API
----------
    load_manifest(skill_dir: Path) -> SkillManifest
    load_skill_body(skill_dir: Path) -> str
    list_skill_resources(skill_dir: Path) -> dict[str, list[ResourceFile]]
    load_resource(resource: ResourceFile) -> str
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ResourceFile:
    """A single file bundled inside a skill's resources/ directory."""

    category: str        # e.g. "scripts", "references", "assets"
    name: str            # filename
    path: Path           # absolute path on disk
    size_bytes: int = 0

    def __post_init__(self) -> None:
        if self.path.exists():
            self.size_bytes = self.path.stat().st_size


@dataclass
class SkillManifest:
    """
    Level-1 metadata parsed from the YAML frontmatter of a SKILL.md file.

    Required fields
    ---------------
    id, name, description

    Optional fields
    ---------------
    triggers        - list of example phrases / keywords that should activate this skill
    capabilities    - list of capability strings shown to the router
    enabled         - whether the skill is active (default True)
    entry_point     - filename of the Python runner, e.g. "skill.py"  (None = LLM-guided)
    function        - function name inside entry_point, e.g. "run"
    license         - SPDX license identifier or free text
    """

    id: str
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    enabled: bool = True
    entry_point: Optional[str] = None   # e.g. "skill.py"
    function: Optional[str] = None      # e.g. "run"
    license: Optional[str] = None

    # Path to the SKILL.md file (set by the loader, not from frontmatter)
    skill_md_path: Optional[Path] = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------ #
    # Convenience properties                                               #
    # ------------------------------------------------------------------ #

    @property
    def has_python_runner(self) -> bool:
        """True when the skill ships a Python entry point."""
        return bool(self.entry_point and self.function)

    @property
    def is_llm_guided(self) -> bool:
        """True when there is no Python runner — the executor uses the SKILL.md body."""
        return not self.has_python_runner


# ---------------------------------------------------------------------------
# Level-1: Parse frontmatter from SKILL.md
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """
    Split a SKILL.md file into (yaml_block, body).
    Returns ('', text) if no frontmatter is found.
    """
    m = _FRONTMATTER_RE.match(text)
    if m:
        return m.group(1), m.group(2)
    return "", text


def load_manifest(skill_dir: Path) -> SkillManifest:
    """
    Parse the SKILL.md frontmatter in *skill_dir* and return a SkillManifest.

    Raises
    ------
    FileNotFoundError  - if SKILL.md does not exist
    ValueError         - if frontmatter is missing or required fields absent
    """
    import yaml  # lazy import so startup isn't slowed for non-skill code paths

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")

    text = skill_md.read_text(encoding="utf-8")
    yaml_block, _ = _split_frontmatter(text)

    if not yaml_block.strip():
        raise ValueError(f"SKILL.md in {skill_dir} has no YAML frontmatter")

    data = yaml.safe_load(yaml_block)
    if not isinstance(data, dict):
        raise ValueError(f"SKILL.md frontmatter in {skill_dir} is not a YAML mapping")

    for required in ("id", "name", "description"):
        if required not in data:
            raise ValueError(
                f"SKILL.md in {skill_dir} is missing required field '{required}'"
            )

    manifest = SkillManifest(
        id=str(data["id"]),
        name=str(data["name"]),
        description=str(data["description"]),
        triggers=list(data.get("triggers", [])),
        capabilities=list(data.get("capabilities", [])),
        enabled=bool(data.get("enabled", True)),
        entry_point=data.get("entry_point"),
        function=data.get("function"),
        license=data.get("license"),
        skill_md_path=skill_md,
    )
    return manifest


# ---------------------------------------------------------------------------
# Level-2: Load the full SKILL.md body
# ---------------------------------------------------------------------------


def load_skill_body(skill_dir: Path) -> str:
    """
    Return the markdown instruction body of a SKILL.md file
    (everything after the closing '---' of the frontmatter).

    Returns an empty string if the file is missing or unreadable.
    """
    skill_md = skill_dir / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        logger.warning(f"[SkillLoader] Cannot read {skill_md}")
        return ""

    _, body = _split_frontmatter(text)
    return body.strip()


# ---------------------------------------------------------------------------
# Level-3: Discover and load bundled resources
# ---------------------------------------------------------------------------

_RESOURCE_CATEGORIES = ("scripts", "references", "assets")


def list_skill_resources(skill_dir: Path) -> dict[str, list[ResourceFile]]:
    """
    Discover files under *skill_dir*/resources/<category>/ and return a
    mapping of {category: [ResourceFile, ...]}.

    Only the standard categories ("scripts", "references", "assets") are
    scanned; unknown sub-folders are ignored.
    """
    resources: dict[str, list[ResourceFile]] = {cat: [] for cat in _RESOURCE_CATEGORIES}
    resources_root = skill_dir / "resources"

    if not resources_root.is_dir():
        return resources

    for category in _RESOURCE_CATEGORIES:
        cat_dir = resources_root / category
        if not cat_dir.is_dir():
            continue
        for file_path in sorted(cat_dir.iterdir()):
            if file_path.is_file():
                resources[category].append(
                    ResourceFile(
                        category=category,
                        name=file_path.name,
                        path=file_path,
                    )
                )

    return resources


def load_resource(resource: ResourceFile) -> str:
    """
    Read and return the text content of a single ResourceFile.
    Returns an empty string if the file cannot be read.
    """
    try:
        return resource.path.read_text(encoding="utf-8")
    except OSError:
        logger.warning(f"[SkillLoader] Cannot read resource {resource.path}")
        return ""
