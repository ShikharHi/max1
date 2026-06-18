"""
max/api/runs.py

The SSE streaming endpoint + history endpoints for time travel.
1. Registers an OTel queue for the run_id
2. Kicks off graph.ainvoke in a background task (so SSE can stream concurrently)
3. Streams OTel span events to the frontend as they arrive
4. Sends a final [DONE] sentinel

Time Travel features:
- GET /threads/{thread_id}/history: list thread checkpoint history
- POST /threads/{thread_id}/runs/stream:
    - Standard execution (no checkpoint_id)
    - Replay (checkpoint_id provided, no fork_values)
    - Fork (checkpoint_id + fork_values provided)
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from max.api.models import SendMessageRequest, CheckpointSnapshotResponse, MessageDict
from max.otel import register_run, unregister_run, close_run
from max.core.snapshots import take_snapshot, restore_snapshot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/threads", tags=["runs"])

# Graph is injected at startup from main.py
_graph = None


def set_graph(graph) -> None:
    global _graph
    _graph = graph


def _message_to_dict(msg) -> dict:
    return {
        "type": getattr(msg, "type", "unknown"),
        "content": getattr(msg, "content", ""),
        "name": getattr(msg, "name", None),
        "id": getattr(msg, "id", None),
    }


@router.get("/{thread_id}/history", response_model=list[CheckpointSnapshotResponse])
async def get_thread_history(thread_id: str, limit: int = 50):
    """List the state checkpoint history for a given thread."""
    if not _graph:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    config = {"configurable": {"thread_id": thread_id}}
    
    # aget_state_history returns an async generator of StateSnapshot objects
    try:
        snapshots = []
        async for s in _graph.aget_state_history(config):
            snapshots.append(s)
    except Exception as e:
        logger.exception(f"Failed to fetch history for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))

    history = []
    for s in snapshots[:limit]:
        # Serialize messages if present in values
        values = dict(s.values)
        if "messages" in values and isinstance(values["messages"], list):
            values["messages"] = [_message_to_dict(m) for m in values["messages"]]

        history.append(
            CheckpointSnapshotResponse(
                checkpoint_id=s.config["configurable"]["checkpoint_id"],
                parent_checkpoint_id=s.parent_config["configurable"]["checkpoint_id"] if s.parent_config else None,
                step=s.metadata.get("step", -1),
                source=s.metadata.get("source", "unknown"),
                created_at=s.created_at,
                next_nodes=list(s.next),
                values=values,
            )
        )
    return history


@router.post("/{thread_id}/runs/stream")
async def stream_run(thread_id: str, req: SendMessageRequest):
    """
    POST a message and stream OTel step events + final response via SSE.

    Time Travel Support:
    - To replay from a past checkpoint: provide `checkpoint_id` and omit `fork_values`.
    - To fork from a past checkpoint: provide `checkpoint_id` and `fork_values`.
    - Normal run: omit `checkpoint_id` and provide `message`.
    """
    if not _graph:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    run_id = req.run_id
    queue = register_run(run_id)

    async def run_graph():
        try:
            assert _graph is not None

            # Base config points to the thread
            base_config = {"configurable": {"thread_id": thread_id}}
            
            # Add run_id to config for OTel
            invoke_config = {**base_config, "run_id": run_id}

            saved_temp_initial = False
            if req.checkpoint_id:
                # --- TIME TRAVEL: Replay or Fork ---
                checkpoint_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": req.checkpoint_id
                    }
                }

                # Restore files to the target checkpoint state
                try:
                    restore_snapshot(thread_id, req.checkpoint_id)
                except Exception as e:
                    logger.warning(f"Failed to restore file snapshot: {e}")

                if req.fork_values:
                    # FORK: update state at checkpoint, then resume
                    logger.info(f"[Runs] Forking thread {thread_id} from {req.checkpoint_id}")
                    # Ensure messages are proper LangChain objects if provided
                    values_to_update = dict(req.fork_values)
                    if "messages" in values_to_update:
                        msgs = []
                        for m in values_to_update["messages"]:
                            if isinstance(m, dict) and "content" in m:
                                msgs.append(HumanMessage(content=m["content"]))
                            else:
                                msgs.append(m)
                        values_to_update["messages"] = msgs

                    fork_config = await _graph.aupdate_state(checkpoint_config, values=values_to_update)
                    # Resume from the fork (input is None)
                    final_state = await _graph.ainvoke(None, config={**fork_config, "run_id": run_id})
                else:
                    # REPLAY: resume directly from checkpoint
                    logger.info(f"[Runs] Replaying thread {thread_id} from {req.checkpoint_id}")
                    final_state = await _graph.ainvoke(None, config={**checkpoint_config, "run_id": run_id})

            else:
                # --- NORMAL EXECUTION ---
                if not req.message:
                    raise ValueError("message is required for standard execution")

                # Take a pre-run file snapshot of current active checkpoint
                try:
                    state = await _graph.aget_state(base_config)
                    if state and state.config and "configurable" in state.config:
                        current_cid = state.config["configurable"].get("checkpoint_id")
                        if current_cid:
                            take_snapshot(thread_id, current_cid)
                        else:
                            take_snapshot(thread_id, "_initial_temp")
                            saved_temp_initial = True
                    else:
                        take_snapshot(thread_id, "_initial_temp")
                        saved_temp_initial = True
                except Exception as e:
                    logger.warning(f"Failed to take pre-run file snapshot: {e}")
                
                initial_state = {
                    "messages": [HumanMessage(content=req.message)],
                    "run_id": run_id,
                    "intent": None,
                    "selected_agent": None,
                    "plan": None,
                    "result": None,
                    "confirmed": None,
                }
                final_state = await _graph.ainvoke(initial_state, config=invoke_config)

                # If we saved the initial temp snapshot, rename it to the actual step -1 checkpoint id
                if saved_temp_initial:
                    try:
                        async for s in _graph.aget_state_history(base_config):
                            if s.metadata.get("step") == -1 or s.parent_config is None:
                                first_cid = s.config["configurable"]["checkpoint_id"]
                                from max.core.snapshots import SNAPSHOT_DIR
                                temp_dir = SNAPSHOT_DIR / thread_id / "_initial_temp"
                                target_dir = SNAPSHOT_DIR / thread_id / first_cid
                                if temp_dir.exists() and not target_dir.exists():
                                    temp_dir.rename(target_dir)
                                break
                    except Exception as e:
                        logger.warning(f"Failed to rename temp snapshot: {e}")

            # Push a result event then close
            result_event = {
                "type": "result",
                "content": final_state.get("result", "") if final_state else "",
                "run_id": run_id,
                "thread_id": thread_id,
            }
            queue.put_nowait({"_result_event": result_event})

        except Exception as e:
            logger.exception(f"[Runs] Graph error for run_id={run_id}")
            queue.put_nowait({"_error": str(e)})
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
