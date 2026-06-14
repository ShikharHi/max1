"""
max/api/runs.py

The SSE streaming endpoint.
1. Registers an OTel queue for the run_id
2. Kicks off graph.ainvoke in a background task (so SSE can stream concurrently)
3. Streams OTel span events to the frontend as they arrive
4. Sends a final [DONE] sentinel
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from max.api.models import SendMessageRequest
from max.otel import register_run, unregister_run, close_run

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/threads", tags=["runs"])

# Graph is injected at startup from main.py
_graph = None


def set_graph(graph) -> None:
    global _graph
    _graph = graph


@router.post("/{thread_id}/runs/stream")
async def stream_run(thread_id: str, req: SendMessageRequest):
    """
    POST a message and stream OTel step events + final response via SSE.

    SSE event format:
      data: {"type": "step", "span_id": ..., "name": ..., "attrs": {...}, ...}
      data: {"type": "result", "content": "..."}
      data: [DONE]
    """
    if not _graph:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    run_id = req.run_id
    queue = register_run(run_id)

    config = {
        "configurable": {"thread_id": thread_id},
        "run_id": run_id,
    }

    initial_state = {
        "messages": [HumanMessage(content=req.message)],
        "run_id": run_id,
        "intent": None,
        "selected_agent": None,
        "plan": None,
        "result": None,
        "confirmed": None,
    }

    async def run_graph():
        try:
            assert _graph is not None
            final_state = await _graph.ainvoke(initial_state, config=config)
            # Push a result event then close
            result_event = {
                "type": "result",
                "content": final_state.get("result", ""),
                "run_id": run_id,
                "thread_id": thread_id,
            }
            queue.put_nowait({"_result_event": result_event})
        except Exception:
            logger.exception(f"[Runs] Graph error for run_id={run_id}")
            queue.put_nowait({"_error": "Graph execution failed"})
        finally:
            close_run(run_id)

    async def event_generator():
        # Start the graph in background
        task = asyncio.create_task(run_graph())

        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)

                if event is None:
                    # Sentinel — stream is done
                    yield "data: [DONE]\n\n"
                    break

                if "_result_event" in event:
                    yield f"data: {json.dumps({'type': 'result', **event['_result_event']})}\n\n"
                    continue

                if "_error" in event:
                    yield f"data: {json.dumps({'type': 'error', 'message': event['_error']})}\n\n"
                    break

                # OTel span event — enrich with type field
                span_event = {"type": "step", **event}
                yield f"data: {json.dumps(span_event)}\n\n"

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout'})}\n\n"
        finally:
            unregister_run(run_id)
            task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
