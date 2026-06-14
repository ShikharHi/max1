"""
max/otel/processor.py

The heart of MAX's framework-agnostic step streaming.

Every agent (LangGraph, CrewAI, raw Python) emits raw OTel spans tagged with
max.run_id. This processor catches span.end() calls synchronously and routes
them into per-run asyncio queues. FastAPI SSEs those queues to the frontend.

Contract every agent must follow:
    tracer = trace.get_tracer("max.agents.your_agent")
    with tracer.start_as_current_span("your.step") as span:
        span.set_attribute("max.run_id", run_id)   # required
        span.set_attribute("max.agent", "your_agent")
        span.set_attribute("max.step", "description of what's happening")
        # ... do work ...
"""

import asyncio
import logging
from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

logger = logging.getLogger(__name__)

# Global registry: run_id → asyncio.Queue
# Populated by the SSE endpoint before the run starts, cleaned up after.
_run_queues: dict[str, asyncio.Queue] = {}
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Call this once at FastAPI startup with the running event loop."""
    global _loop
    _loop = loop


def register_run(run_id: str) -> asyncio.Queue:
    """Create a queue for a run. Call before starting the agent."""
    q: asyncio.Queue = asyncio.Queue()
    _run_queues[run_id] = q
    logger.debug(f"[OTel] Registered queue for run_id={run_id}")
    return q


def unregister_run(run_id: str) -> None:
    """Remove a run's queue. Call after SSE stream closes."""
    _run_queues.pop(run_id, None)
    logger.debug(f"[OTel] Unregistered queue for run_id={run_id}")


def close_run(run_id: str) -> None:
    """Send a sentinel None to signal the stream is done."""
    q = _run_queues.get(run_id)
    if q and _loop:
        _loop.call_soon_threadsafe(q.put_nowait, None)


class MaxSpanProcessor(SpanProcessor):
    """
    Synchronous SpanProcessor that bridges OTel span.end() → asyncio.Queue.

    on_end is called synchronously on whatever thread ends the span.
    We use call_soon_threadsafe to safely hand off to the asyncio event loop.
    """

    def on_start(self, span, parent_context=None) -> None:
        # Optionally emit "started" events here if you want real-time start signals.
        # For now we emit on_end so we have duration + status.
        pass

    def on_end(self, span: ReadableSpan) -> None:
        try:
            attrs = dict(span.attributes or {})
            run_id = attrs.get("max.run_id")
            if not run_id:
                return  # span not tagged for MAX — ignore

            q = _run_queues.get(run_id)
            if not q:
                return  # no active SSE consumer for this run

            event = {
                "span_id": format(span.context.span_id, "016x"),
                "parent_id": (
                    format(span.parent.span_id, "016x") if span.parent else None
                ),
                "name": span.name,
                "attrs": attrs,
                "status": span.status.status_code.name,
                "duration_ms": (
                    (span.end_time - span.start_time) // 1_000_000
                    if span.end_time and span.start_time
                    else 0
                ),
            }

            if _loop and _loop.is_running():
                _loop.call_soon_threadsafe(q.put_nowait, event)
            else:
                logger.warning(
                    f"[OTel] Event loop not available, dropping span={span.name}"
                )

        except Exception:
            logger.exception("[OTel] Error in MaxSpanProcessor.on_end")

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
