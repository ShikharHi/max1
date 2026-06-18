"""
max/main_cli.py  --  Rich terminal chat client for the MAX server.

Connects to the running MAX API server (main.py) and provides an
interactive chat experience with thread management and plugin control.

Usage:
    python -m max.main_cli
    python -m max.main_cli --port 8000

Slash commands inside the chat:
    /new [title]        Create a new conversation thread
    /threads            List all threads
    /switch <n>         Switch to thread by number
    /rename <title>     Rename current thread
    /delete             Delete current thread
    /plugins            List plugins and their status
    /toggle <id>        Toggle a plugin on/off
    /history            List the state checkpoint history of the thread
    /replay <id>        Replay execution from a specific checkpoint
    /fork <id> <msg>    Fork from a checkpoint with a new message
    /info               Show server health + current thread
    /clear              Clear the terminal
    /help               Show slash-command help
    /quit               Exit
"""

import asyncio
import io
import json
import os
import sys
import uuid
from pathlib import Path

import click
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.rule import Rule
from rich.align import Align
from rich.style import Style
from rich.markup import escape
from rich.markdown import Markdown
from rich.prompt import Prompt

# ── Env ───────────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")

from max.core.snapshots import restore_snapshot

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(force_terminal=True)

# ── Constants ─────────────────────────────────────────────────────────────────
VERSION = "0.1.0"
GRADIENT = ["#6C63FF", "#B06AB3", "#FF6584"]

BANNER = r"""
    ╔╦╗╔═╗═╗ ╦
    ║║║╠═╣╔╩╦╝
    ╩ ╩╩ ╩╩ ╚═
"""

STEP_ICONS = {
    "router":      ("bold bright_cyan",   ">>"),
    "executor":    ("bold bright_yellow",  "::"),
    "synthesizer": ("bold bright_green",   "<<"),
}

HELP_TEXT = """
[bold bright_cyan]Slash Commands[/bold bright_cyan]

  [cyan]/new[/cyan] [dim][title][/dim]        Create a new conversation thread
  [cyan]/threads[/cyan]             List all threads
  [cyan]/switch[/cyan] [dim]<n>[/dim]          Switch to thread N (from /threads)
  [cyan]/rename[/cyan] [dim]<title>[/dim]      Rename the current thread
  [cyan]/delete[/cyan]              Delete the current thread
  [cyan]/plugins[/cyan]             List plugins and their status
  [cyan]/toggle[/cyan] [dim]<id>[/dim]         Toggle a plugin on/off
  [cyan]/history[/cyan]             List user-friendly input checkpoint history
  [cyan]/undo[/cyan] [dim][idx][/dim]          Undo the input at index (and everything after it)
  [cyan]/fork[/cyan] [dim]<idx/id> <msg>[/dim]  Fork execution with a new message
  [cyan]/info[/cyan]                Server health + current thread
  [cyan]/clear[/cyan]               Clear the terminal
  [cyan]/help[/cyan]                Show this help
  [cyan]/quit[/cyan]                Exit the chat
"""


# ══════════════════════════════════════════════════════════════════════════════
#  Display helpers
# ══════════════════════════════════════════════════════════════════════════════


def _gradient(text: str) -> Text:
    rich = Text()
    n = max(len(text) - 1, 1)
    for i, ch in enumerate(text):
        idx = int(i / n * (len(GRADIENT) - 1))
        rich.append(ch, style=Style(color=GRADIENT[min(idx, len(GRADIENT) - 1)], bold=True))
    return rich


def _banner() -> Panel:
    lines = BANNER.strip("\n").split("\n")
    block = Text()
    for line in lines:
        block.append_text(_gradient(line))
        block.append("\n")
    block.append(f"Terminal client  v{VERSION}\n", style="dim italic")
    return Panel(Align.center(block), border_style="bright_blue", box=box.DOUBLE_EDGE, padding=(0, 2))


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP client — talks to the running MAX server (main.py)
# ══════════════════════════════════════════════════════════════════════════════


class MaxClient:
    """Async HTTP wrapper for the MAX REST API."""

    def __init__(self, base_url: str):
        import httpx
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def close(self):
        await self._http.aclose()

    # ── health ────────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        r = await self._http.get("/health")
        r.raise_for_status()
        return r.json()

    # ── threads ───────────────────────────────────────────────────────────────

    async def create_thread(self, title: str = "") -> dict:
        meta = {"title": title} if title else {}
        r = await self._http.post("/threads", json={"metadata": meta})
        r.raise_for_status()
        return r.json()

    async def list_threads(self, limit: int = 20) -> list[dict]:
        r = await self._http.get("/threads", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    async def rename_thread(self, thread_id: str, title: str) -> dict:
        r = await self._http.patch(f"/threads/{thread_id}", json={"title": title})
        r.raise_for_status()
        return r.json()

    async def delete_thread(self, thread_id: str) -> dict:
        r = await self._http.delete(f"/threads/{thread_id}")
        r.raise_for_status()
        return r.json()

    # ── plugins ───────────────────────────────────────────────────────────────

    async def list_plugins(self) -> list[dict]:
        r = await self._http.get("/plugins")
        r.raise_for_status()
        return r.json()

    async def toggle_plugin(self, plugin_id: str, enabled: bool) -> dict:
        r = await self._http.patch(f"/plugins/{plugin_id}/toggle", json={"enabled": enabled})
        r.raise_for_status()
        return r.json()

    # ── time travel ───────────────────────────────────────────────────────────

    async def get_history(self, thread_id: str, limit: int = 20) -> list[dict]:
        r = await self._http.get(f"/threads/{thread_id}/history", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    # ── streaming message ─────────────────────────────────────────────────────

    async def stream_message(self, thread_id: str, message: str = None, checkpoint_id: str = None, fork_values: dict = None):
        """POST to /threads/{id}/runs/stream and yield parsed SSE events."""
        import httpx

        run_id = str(uuid.uuid4())
        url = f"{self.base_url}/threads/{thread_id}/runs/stream"
        payload = {"run_id": run_id}
        if message:
            payload["message"] = message
        if checkpoint_id:
            payload["checkpoint_id"] = checkpoint_id
        if fork_values:
            payload["fork_values"] = fork_values

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as c:
            async with c.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        return
                    try:
                        yield json.loads(payload)
                    except json.JSONDecodeError:
                        continue


# ══════════════════════════════════════════════════════════════════════════════
#  Chat session  — the interactive REPL
# ══════════════════════════════════════════════════════════════════════════════


class ChatSession:

    def __init__(self, base_url: str):
        self.client = MaxClient(base_url)
        self.base_url = base_url
        self.thread_id: str | None = None
        self.thread_title: str = "untitled"
        self._cache: list[dict] = []
        self.active_checkpoint_id: str | None = None

    # ── helpers ───────────────────────────────────────────────────────────────

    def _label(self) -> str:
        if not self.thread_id:
            return "[dim]no thread[/dim]"
        return f"[bright_cyan]{self.thread_title}[/bright_cyan] [dim]({self.thread_id[:8]})[/dim]"

    # ── slash commands ────────────────────────────────────────────────────────

    async def cmd_new(self, args: str):
        title = args.strip()
        try:
            data = await self.client.create_thread(title)
            self.thread_id = data["thread_id"]
            self.thread_title = data.get("metadata", {}).get("title", "") or "untitled"
            self.active_checkpoint_id = None
            console.print(f"  [green]+[/green] Created thread {self._label()}")
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")

    async def cmd_threads(self, _a: str):
        try:
            self._cache = await self.client.list_threads()
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
            return

        if not self._cache:
            console.print("  [dim]No threads. Use /new to create one.[/dim]")
            return

        t = Table(box=box.SIMPLE_HEAVY, border_style="dim", header_style="bold bright_cyan", pad_edge=True)
        t.add_column("#", style="bold yellow", width=4, justify="right")
        t.add_column("Title", style="white", min_width=20)
        t.add_column("Thread ID", style="dim", no_wrap=True)
        t.add_column("Created", style="dim")
        t.add_column("", width=3)

        for i, th in enumerate(self._cache, 1):
            title = th.get("metadata", {}).get("title", "") or "untitled"
            tid = th["thread_id"]
            created = th.get("created_at", "")[:19].replace("T", " ")
            active = tid == self.thread_id
            marker = "[bright_green]<--[/bright_green]" if active else ""
            t.add_row(str(i), title, tid[:12] + "...", created, marker, style="on grey11" if active else "")

        console.print(t)
        console.print("  [dim]Use[/dim] [cyan]/switch N[/cyan] [dim]to switch threads.[/dim]")

    async def cmd_switch(self, args: str):
        n = args.strip()
        if not n.isdigit():
            console.print("  [red]Usage:[/red] /switch <number>")
            return
        if not self._cache:
            try:
                self._cache = await self.client.list_threads()
            except Exception as e:
                console.print(f"  [red]Error:[/red] {e}")
                return
        idx = int(n) - 1
        if idx < 0 or idx >= len(self._cache):
            console.print(f"  [red]Invalid. Range: 1-{len(self._cache)}[/red]")
            return
        th = self._cache[idx]
        self.thread_id = th["thread_id"]
        self.thread_title = th.get("metadata", {}).get("title", "") or "untitled"
        self.active_checkpoint_id = None
        console.print(f"  [green]Switched to[/green] {self._label()}")

    async def cmd_rename(self, args: str):
        if not self.thread_id:
            console.print("  [red]No active thread.[/red]")
            return
        title = args.strip()
        if not title:
            console.print("  [red]Usage:[/red] /rename <new title>")
            return
        try:
            await self.client.rename_thread(self.thread_id, title)
            self.thread_title = title
            console.print(f"  [green]Renamed to[/green] {self._label()}")
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")

    async def cmd_delete(self, _a: str):
        if not self.thread_id:
            console.print("  [red]No active thread.[/red]")
            return
        label = self._label()
        ans = Prompt.ask(f"  Delete {label}? [y/N]", default="n", console=console)
        if ans.lower() != "y":
            console.print("  [dim]Cancelled.[/dim]")
            return
        try:
            await self.client.delete_thread(self.thread_id)
            console.print(f"  [red]Deleted[/red] {label}")
            self.thread_id = None
            self.thread_title = "untitled"
            self.active_checkpoint_id = None
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")

    async def cmd_plugins(self, _a: str):
        try:
            plugins = await self.client.list_plugins()
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
            return
        if not plugins:
            console.print("  [dim]No plugins.[/dim]")
            return

        t = Table(box=box.SIMPLE_HEAVY, border_style="dim", header_style="bold bright_green", pad_edge=True)
        t.add_column("ID", style="cyan", no_wrap=True)
        t.add_column("Name", style="white")
        t.add_column("Type", style="magenta")
        t.add_column("Status", justify="center")
        t.add_column("Capabilities", style="dim")

        for p in plugins:
            st = "[green]ON[/green]" if p.get("enabled") else "[red]OFF[/red]"
            t.add_row(p["id"], p.get("name", ""), p.get("type", ""), st, ", ".join(p.get("capabilities", [])))
        console.print(t)
        console.print("  [dim]Use[/dim] [cyan]/toggle <id>[/cyan] [dim]to enable/disable.[/dim]")

    async def cmd_toggle(self, args: str):
        pid = args.strip()
        if not pid:
            console.print("  [red]Usage:[/red] /toggle <plugin_id>")
            return
        try:
            plugins = await self.client.list_plugins()
            target = next((p for p in plugins if p["id"] == pid), None)
            if not target:
                console.print(f"  [red]Plugin '{pid}' not found.[/red]")
                return
            new = not target.get("enabled", True)
            await self.client.toggle_plugin(pid, new)
            console.print(f"  [cyan]{pid}[/cyan] is now {'[green]ON[/green]' if new else '[red]OFF[/red]'}")
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")

    async def cmd_history(self, _a: str):
        if not self.thread_id:
            console.print("  [red]No active thread.[/red]")
            return
        try:
            history = await self.client.get_history(self.thread_id)
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
            return
        
        if not history:
            console.print("  [dim]No history found.[/dim]")
            return

        # Reconstruct user-friendly turns (user inputs only)
        user_turns = []
        for ch in history:
            if "router" in ch.get("next_nodes", []):
                vals = ch.get("values", {})
                msgs = vals.get("messages", [])
                
                # Find the human message
                human_msgs = [m for m in msgs if m.get("type") == "human"]
                if human_msgs:
                    msg_text = human_msgs[-1].get("content", "")
                    if msg_text:
                        # Deduplicate by checkpoint_id
                        if not any(turn["checkpoint_id"] == ch["checkpoint_id"] for turn in user_turns):
                            user_turns.append({
                                "checkpoint_id": ch["checkpoint_id"],
                                "parent_checkpoint_id": ch.get("parent_checkpoint_id"),
                                "message": msg_text,
                                "step": ch["step"],
                                "next_nodes": ch.get("next_nodes", [])
                            })
        # Reverse to chronological order (oldest first)
        user_turns.reverse()

        if not user_turns:
            console.print("  [dim]No user inputs found in history.[/dim]")
            return

        t = Table(box=box.SIMPLE_HEAVY, border_style="dim", header_style="bold magenta", pad_edge=True)
        t.add_column("Idx", style="yellow", width=4, justify="right")
        t.add_column("User Input", style="white", min_width=30)
        t.add_column("Checkpoint ID", style="cyan", width=15)

        # Cache these for undo/fork references
        self._history_cache = user_turns

        for idx, turn in enumerate(user_turns, 1):
            t.add_row(str(idx), escape(turn["message"]), turn["checkpoint_id"][:12])

        console.print(t)
        console.print("  [dim]Use [cyan]/undo <idx>[/cyan] to undo that input (and everything after it),[/dim]")
        console.print("  [dim]or [cyan]/fork <idx> <msg>[/cyan] to fork with a new input from that point.[/dim]")

    async def cmd_undo(self, args: str):
        if not self.thread_id:
            console.print("  [red]No active thread.[/red]")
            return
        
        # Load history to find checkpoints
        try:
            history = await self.client.get_history(self.thread_id)
        except Exception as e:
            console.print(f"  [red]Error fetching history:[/red] {e}")
            return

        # Reconstruct user_turns exactly like in cmd_history
        user_turns = []
        for ch in history:
            if "router" in ch.get("next_nodes", []):
                vals = ch.get("values", {})
                msgs = vals.get("messages", [])
                human_msgs = [m for m in msgs if m.get("type") == "human"]
                if human_msgs:
                    msg_text = human_msgs[-1].get("content", "")
                    if msg_text:
                        if not any(t["checkpoint_id"] == ch["checkpoint_id"] for t in user_turns):
                            user_turns.append(ch)

        user_turns.reverse()

        if not user_turns:
            console.print("  [dim]No inputs to undo.[/dim]")
            return

        args = args.strip()
        if not args:
            # Default to undoing the LAST input
            idx = len(user_turns)
        else:
            if not args.isdigit():
                console.print("  [red]Usage:[/red] /undo [index]")
                return
            idx = int(args)
            if idx < 1 or idx > len(user_turns):
                console.print(f"  [red]Invalid index. Range: 1-{len(user_turns)}[/red]")
                return

        target_checkpoint = user_turns[idx - 1]
        cid = target_checkpoint.get("parent_checkpoint_id") or target_checkpoint["checkpoint_id"]

        console.print(f"  [magenta]Undoing input and reverting to state before checkpoint {cid[:12]}...[/magenta]")
        
        # 1. Ask the server to prune the database checkpoints/writes
        try:
            await self.client.revert_thread(self.thread_id, cid)
        except Exception as e:
            console.print(f"  [yellow]Note: Could not revert server thread state: {e}[/yellow]")

        # 2. Restore files to the target checkpoint state immediately
        try:
            restore_snapshot(self.thread_id, cid)
            console.print("  [green]Workspace files successfully reverted to target state.[/green]")
        except Exception as e:
            console.print(f"  [yellow]Note: Could not restore file snapshot: {e}[/yellow]")

        # Update the active checkpoint ID so the next message forks from here
        self.active_checkpoint_id = cid
        console.print(f"  [green]State reverted. Ready for new input.[/green]")

    async def cmd_replay(self, args: str):
        if not self.thread_id:
            console.print("  [red]No active thread.[/red]")
            return
        cid = args.strip()
        if not cid:
            console.print("  [red]Usage:[/red] /replay <checkpoint_id>")
            return
        
        console.print(f"  [magenta]Replaying from checkpoint {cid}...[/magenta]")
        await self._do_stream(message=None, checkpoint_id=cid, fork_values=None)

    async def cmd_fork(self, args: str):
        if not self.thread_id:
            console.print("  [red]No active thread.[/red]")
            return
        
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            console.print("  [red]Usage:[/red] /fork <idx_or_checkpoint_id> <new message>")
            return
        
        target = parts[0]
        msg = parts[1]

        # Check if the target is an index from the history cache
        cid = target
        if target.isdigit() and hasattr(self, "_history_cache"):
            idx = int(target)
            if 1 <= idx <= len(self._history_cache):
                cid = self._history_cache[idx - 1]["checkpoint_id"]

        console.print(f"  [magenta]Forking from checkpoint {cid[:12]} with new message...[/magenta]")
        fork_values = {"messages": [{"type": "human", "content": msg}]}
        await self._do_stream(message=None, checkpoint_id=cid, fork_values=fork_values)

    async def cmd_info(self, _a: str):
        try:
            h = await self.client.health()
            st = "[green]ok[/green]" if h.get("status") == "ok" else f"[red]{h.get('status')}[/red]"
            console.print(f"  Server:  {self.base_url}  [{st}]")
        except Exception as e:
            console.print(f"  [red]Server unreachable:[/red] {e}")
        console.print(f"  Thread:  {self._label()}")

    async def cmd_help(self, _a: str):
        console.print(Panel(
            HELP_TEXT.strip(), border_style="bright_cyan", box=box.ROUNDED,
            title="[bold]Help[/bold]", title_align="left", padding=(1, 2),
        ))

    async def cmd_clear(self, _a: str):
        console.clear()
        console.print(_banner())
        console.print()

    # ── send message & stream response ────────────────────────────────────────

    async def _do_stream(self, message: str = None, checkpoint_id: str = None, fork_values: dict = None):
        assert self.thread_id is not None
        steps = 0
        result = ""
        error = ""

        try:
            with console.status("[bold bright_cyan]Thinking...[/bold bright_cyan]", spinner="dots"):
                async for event in self.client.stream_message(self.thread_id, message, checkpoint_id, fork_values):
                    etype = event.get("type", "")

                    if etype == "step":
                        steps += 1
                        name = event.get("name", "step")
                        style, icon = STEP_ICONS.get(name, ("bold white", "**"))
                        attrs = event.get("attributes", event.get("attrs", {}))

                        parts = []
                        for key in ("intent", "selected_agent", "plan", "tool", "action"):
                            val = attrs.get(key)
                            if val:
                                parts.append(f"[dim]{key}=[/dim]{escape(str(val))}")
                        detail = "  ".join(parts)
                        console.print(f"  [{style}]{icon} {name}[/{style}]  {detail}")

                    elif etype == "result":
                        result = event.get("content", "")

                    elif etype == "error":
                        error = event.get("message", "Unknown error")

        except Exception as e:
            error = str(e)

        console.print()

        if error:
            console.print(Panel(
                f"[red]{escape(error)}[/red]",
                title="[bold red]Error[/bold red]", title_align="left",
                border_style="red", box=box.ROUNDED, padding=(0, 1),
            ))
        elif result:
            try:
                md = Markdown(result)
            except Exception:
                md = escape(result)
            console.print(Panel(
                md,
                title="[bold bright_green]MAX[/bold bright_green]", title_align="left",
                border_style="bright_green", box=box.ROUNDED, padding=(0, 1),
            ))
            if steps:
                console.print(f"  [dim]({steps} agent steps)[/dim]")
        else:
            console.print("  [dim]No response.[/dim]")

        console.print()


    async def send(self, message: str):
        # Auto-create thread on first message
        if not self.thread_id:
            words = message.split()[:6]
            title = " ".join(words)
            if len(title) > 40:
                title = title[:37] + "..."
            try:
                data = await self.client.create_thread(title)
                self.thread_id = data["thread_id"]
                self.thread_title = data.get("metadata", {}).get("title", "") or title
                console.print(f"  [dim]New thread:[/dim] {self._label()}")
                console.print()
            except Exception as e:
                console.print(f"  [red]Cannot create thread:[/red] {e}")
                return

        # Show user message
        console.print(Panel(
            escape(message),
            title="[bold bright_magenta]You[/bold bright_magenta]",
            title_align="left", border_style="bright_magenta",
            box=box.ROUNDED, padding=(0, 1),
        ))
        console.print()

        if self.active_checkpoint_id:
            cid = self.active_checkpoint_id
            self.active_checkpoint_id = None
            await self._do_stream(message=None, checkpoint_id=cid, fork_values={"messages": [{"type": "human", "content": message}]})
        else:
            await self._do_stream(message=message)

    # ── main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        console.print(_banner())
        console.print()

        # Connectivity check
        try:
            await self.client.health()
            console.print(f"  [green]Connected[/green] to MAX server at [bold]{self.base_url}[/bold]")
        except Exception:
            console.print(f"  [red]Cannot reach server[/red] at [bold]{self.base_url}[/bold]")
            console.print("  [dim]Start the server first:  uvicorn max.main:app --reload --port 8000[/dim]")
            await self.client.close()
            return

        # Auto-load most recent thread on startup
        try:
            self._cache = await self.client.list_threads()
            if self._cache:
                th = self._cache[0]
                self.thread_id = th["thread_id"]
                self.thread_title = th.get("metadata", {}).get("title", "") or "untitled"
                console.print(f"  [green]Loaded most recent thread:[/green] {self._label()}")
        except Exception:
            pass

        console.print("  [dim]Type a message to chat, or[/dim] [cyan]/help[/cyan] [dim]for commands.[/dim]")
        console.print("  [dim]A thread will be created automatically on your first message.[/dim]")
        console.print()
        console.print(Rule(style="dim"))
        console.print()

        dispatch = {
            "/new": self.cmd_new, "/threads": self.cmd_threads,
            "/switch": self.cmd_switch, "/rename": self.cmd_rename,
            "/delete": self.cmd_delete, "/plugins": self.cmd_plugins,
            "/toggle": self.cmd_toggle, "/history": self.cmd_history,
            "/undo": self.cmd_undo,
            "/replay": self.cmd_replay, "/fork": self.cmd_fork,
            "/info": self.cmd_info,
            "/help": self.cmd_help, "/clear": self.cmd_clear,
        }

        try:
            while True:
                try:
                    prompt = f"max ({self.thread_title}) > " if self.thread_id else "max > "
                    text = console.input(f"[bright_magenta]{escape(prompt)}[/bright_magenta]").strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not text:
                    continue
                if text.lower() in ("/quit", "/exit", "/q"):
                    break

                if text.startswith("/"):
                    parts = text.split(maxsplit=1)
                    cmd = parts[0].lower()
                    arg = parts[1] if len(parts) > 1 else ""
                    handler = dispatch.get(cmd)
                    if handler:
                        await handler(arg)
                    else:
                        console.print(f"  [red]Unknown command:[/red] {cmd}  [dim](/help for list)[/dim]")
                    console.print()
                    continue

                await self.send(text)

        finally:
            await self.client.close()
            console.print()
            console.print(Panel("[bold]Goodbye![/bold]", border_style="bright_blue", box=box.ROUNDED, padding=(0, 2)))


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════


@click.command()
@click.option("--host", default=None, help="Server host (default: from .env or 127.0.0.1)")
@click.option("--port", "-p", default=None, type=int, help="Server port (default: from .env or 8000)")
def main(host, port):
    """MAX terminal chat -- connects to the running MAX server."""
    host = host or os.getenv("MAX_HOST", "127.0.0.1")
    port = port or int(os.getenv("MAX_PORT", "8000"))
    asyncio.run(ChatSession(f"http://{host}:{port}").run())


if __name__ == "__main__":
    main()
