"""
max/main.py — FastAPI application entry point.

Startup order:
1. OTel provider initialized (must be first)
2. AsyncSqliteSaver created
3. LangGraph compiled with checkpointer
4. Graph injected into runs router
5. Event loop registered with OTel processor
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DATABASE_PATH", "./max.db"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register the running event loop with the OTel processor
    loop = asyncio.get_running_loop()
    set_event_loop(loop)

    # Build graph with async SQLite checkpointer
    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        graph = build_graph(checkpointer)
        set_graph(graph)
        logger.info("✅ MAX graph compiled and ready")
        yield

    logger.info("🛑 MAX shutting down")


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
    return {"status": "ok", "service": "MAX"}
