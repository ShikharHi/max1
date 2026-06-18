"""
max/main.py — FastAPI application entry point.

Startup order:
1. OTel provider initialized (must be first)
2. Plugin registry scanned (discovers skills, tools, agents, mcp)
3. MCP manager started (connects to MCP servers)
4. MCP runners registered into registry
5. AsyncSqliteSaver created
6. LangGraph compiled with checkpointer
7. Graph injected into runs router
8. Event loop registered with OTel processor
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# OTel MUST be initialized before any agent imports
from max.otel import setup_otel, set_event_loop
setup_otel()

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from max.core.graph import build_graph
from max.api import threads_router, runs_router, plugins_router, set_graph
from max.plugins import registry, mcp_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DATABASE_PATH", "./max.db"))


def _register_mcp_runners() -> None:
    """Wire MCP tool runners into the registry after mcp_manager starts."""
    from max.api.plugins import _register_mcp_runners as _do_register
    _do_register()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register the running event loop with the OTel processor
    loop = asyncio.get_running_loop()
    set_event_loop(loop)

    # 1. Scan all plugin directories (skills, tools, agents subfolders, mcp)
    logger.info("🔍 Scanning plugins...")
    registry.scan()
    logger.info(f"✅ Registry loaded {len(registry.get_all())} plugin(s)")

    # 2. Start MCP manager — connect to all enabled MCP servers
    logger.info("🔌 Starting MCP manager...")
    await mcp_manager.start()
    if mcp_manager.is_ready():
        logger.info(f"✅ MCP manager ready — {len(mcp_manager.get_tools())} tool(s) loaded")
        # 3. Wire MCP runners into the registry
        _register_mcp_runners()
    else:
        logger.info("ℹ️  MCP manager not started (no servers configured or langchain-mcp-adapters not installed)")

    # 4. Build graph with async SQLite checkpointer
    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        graph = build_graph(checkpointer)
        set_graph(graph)
        logger.info("✅ MAX graph compiled and ready")
        yield

    # Shutdown
    logger.info("🛑 MAX shutting down")
    await mcp_manager.stop()
    logger.info("✅ MCP manager stopped")


app = FastAPI(
    title="MAX API",
    description="Framework-agnostic multi-agent platform with OTel step streaming",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads_router)
app.include_router(runs_router)
app.include_router(plugins_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "MAX",
        "plugins": len(registry.get_all()),
        "mcp_tools": len(mcp_manager.get_tools()),
    }
