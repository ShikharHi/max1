"""
max/otel/setup.py

Initialize the global TracerProvider with MaxSpanProcessor once at startup.
Import and call setup_otel() before any agent code runs.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from .processor import MaxSpanProcessor

_initialized = False


def setup_otel() -> None:
    global _initialized
    if _initialized:
        return
    provider = TracerProvider()
    provider.add_span_processor(MaxSpanProcessor())
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: str):
    return trace.get_tracer(name)
