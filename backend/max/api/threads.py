"""
max/api/threads.py — Thread CRUD endpoints.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import os

from fastapi import APIRouter, HTTPException

from max.api.models import CreateThreadRequest, ThreadResponse

router = APIRouter(prefix="/threads", tags=["threads"])

DB_PATH = Path(os.getenv("DATABASE_PATH", "./max.db"))


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_threads_table():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.commit()


_init_threads_table()


@router.post("", response_model=ThreadResponse)
def create_thread(req: CreateThreadRequest):
    thread_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO threads (thread_id, created_at, metadata) VALUES (?, ?, ?)",
            (thread_id, created_at, json.dumps(req.metadata)),
        )
        conn.commit()
    return ThreadResponse(
        thread_id=thread_id,
        created_at=created_at,
        metadata=req.metadata,
    )


@router.get("", response_model=list[ThreadResponse])
def list_threads(limit: int = 50):
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM threads ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        ThreadResponse(
            thread_id=r["thread_id"],
            created_at=r["created_at"],
            metadata=json.loads(r["metadata"]),
        )
        for r in rows
    ]


@router.get("/{thread_id}", response_model=ThreadResponse)
def get_thread(thread_id: str):
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM threads WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadResponse(
        thread_id=row["thread_id"],
        created_at=row["created_at"],
        metadata=json.loads(row["metadata"]),
    )


@router.delete("/{thread_id}")
def delete_thread(thread_id: str):
    with _get_conn() as conn:
        conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
        conn.commit()
    return {"deleted": thread_id}


@router.patch("/{thread_id}")
def rename_thread(thread_id: str, body: dict):
    title = body.get("title", "")
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT metadata FROM threads WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Thread not found")
        meta = json.loads(row["metadata"])
        meta["title"] = title
        conn.execute(
            "UPDATE threads SET metadata = ? WHERE thread_id = ?",
            (json.dumps(meta), thread_id),
        )
        conn.commit()
    return {"thread_id": thread_id, "title": title}
