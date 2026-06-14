"""
max/agents/file_manager.py

FileManager subagent — pure Python, OTel-instrumented.
No LangGraph here — this is the point: any framework can be a subagent.

Hard-blocks: node_modules, .git, __pycache__, *.lock, /etc, /sys, /proc
"""

import logging
import os
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from max.otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("max.agents.file_manager")

_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

# Blocked path patterns — never operate on these
BLOCKED_PATTERNS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".lock",
    "/etc",
    "/sys",
    "/proc",
    "/boot",
    "*.pyc",
}

SAFE_ROOT = Path(os.getenv("FILE_MANAGER_ROOT", str(Path.home() / "max_workspace")))


def _is_safe_path(path: Path) -> bool:
    """Validate path is within safe root and not blocked."""
    try:
        path.resolve().relative_to(SAFE_ROOT.resolve())
    except ValueError:
        return False
    path_str = str(path)
    return not any(blocked in path_str for blocked in BLOCKED_PATTERNS)


def _list_files(path: Path, max_depth: int = 2, current_depth: int = 0) -> list[str]:
    if current_depth >= max_depth or not path.is_dir():
        return []
    entries = []
    try:
        for item in sorted(path.iterdir()):
            if not _is_safe_path(item):
                continue
            prefix = "  " * current_depth
            entries.append(f"{prefix}{'📁' if item.is_dir() else '📄'} {item.name}")
            if item.is_dir():
                entries.extend(_list_files(item, max_depth, current_depth + 1))
    except PermissionError:
        entries.append(f"  {'  ' * current_depth}[permission denied]")
    return entries


def _read_file(path: Path, max_bytes: int = 16_000) -> str:
    if not path.is_file():
        return f"Error: {path} is not a file"
    if not _is_safe_path(path):
        return f"Error: {path} is blocked"
    content = path.read_bytes()[:max_bytes]
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return f"[binary file, {len(content)} bytes]"


def _write_file(path: Path, content: str) -> str:
    if not _is_safe_path(path):
        return f"Error: {path} is blocked"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {path}"


def run_file_manager(user_message: str, plan: str, run_id: str) -> str:
    """
    Entry point for the FileManager subagent.
    OTel spans here are picked up by MaxSpanProcessor and streamed to frontend.
    """
    SAFE_ROOT.mkdir(parents=True, exist_ok=True)

    with tracer.start_as_current_span("file_manager.run") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent", "file_manager")
        span.set_attribute("max.step", "Starting file manager")
        span.set_attribute("max.plan", plan)

        # Step 1: Understand the operation needed
        with tracer.start_as_current_span("file_manager.parse_intent") as s:
            s.set_attribute("max.run_id", run_id)
            s.set_attribute("max.agent", "file_manager")
            s.set_attribute("max.step", "Parsing file operation intent")

            parse_response = _llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are a file manager assistant. Parse the user's request "
                            "and respond ONLY with JSON:\n"
                            '{"operation": "list|read|write|search", '
                            '"path": "relative path from workspace root", '
                            '"content": "content to write if operation=write, else null"}\n\n'
                            f"Workspace root: {SAFE_ROOT}\n"
                            "For list: path is the directory to list.\n"
                            "For read: path is the file to read.\n"
                            "For write: path is destination, content is the text.\n"
                            "For search: path is the query term."
                        )
                    ),
                    HumanMessage(content=user_message),
                ]
            )

            raw = parse_response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            import json

            try:
                parsed = json.loads(raw.strip())
                operation = parsed.get("operation", "list")
                rel_path = parsed.get("path", ".")
                content = parsed.get("content")
            except Exception:
                logger.exception("[FileManager] Failed to parse intent")
                operation = "list"
                rel_path = "."
                content = None

            s.set_attribute("max.operation", operation)
            s.set_attribute("max.path", rel_path)

        # Step 2: Execute the operation
        with tracer.start_as_current_span(f"file_manager.{operation}") as s:
            s.set_attribute("max.run_id", run_id)
            s.set_attribute("max.agent", "file_manager")
            s.set_attribute("max.step", f"Executing: {operation} on {rel_path}")

            target = SAFE_ROOT / rel_path

            if operation == "list":
                if not _is_safe_path(target):
                    result = f"Blocked: cannot access {rel_path}"
                else:
                    entries = _list_files(target)
                    result = (
                        f"Contents of {rel_path}:\n" + "\n".join(entries)
                        if entries
                        else f"Directory {rel_path} is empty"
                    )

            elif operation == "read":
                if not _is_safe_path(target):
                    result = f"Blocked: cannot read {rel_path}"
                else:
                    result = _read_file(target)

            elif operation == "write":
                if not content:
                    result = "Error: no content provided for write operation"
                elif not _is_safe_path(target):
                    result = f"Blocked: cannot write to {rel_path}"
                else:
                    result = _write_file(target, content)

            elif operation == "search":
                with tracer.start_as_current_span("file_manager.search_scan") as ss:
                    ss.set_attribute("max.run_id", run_id)
                    ss.set_attribute("max.agent", "file_manager")
                    ss.set_attribute("max.step", f"Scanning files for: {rel_path}")
                    matches = []
                    query = rel_path.lower()
                    for f in SAFE_ROOT.rglob("*"):
                        if f.is_file() and _is_safe_path(f) and query in f.name.lower():
                            matches.append(str(f.relative_to(SAFE_ROOT)))
                    result = (
                        f"Found {len(matches)} file(s) matching '{rel_path}':\n"
                        + "\n".join(matches[:50])
                        if matches
                        else f"No files found matching '{rel_path}'"
                    )
            else:
                result = f"Unknown operation: {operation}"

            s.set_attribute("max.result_preview", result[:200])

        span.set_attribute("max.result_preview", result[:200])
        return result
