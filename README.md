# MAX — Multi-Agent eXecutor

> Framework-agnostic multi-agent platform with OpenTelemetry step streaming.

## Architecture

```
User Message
     │
     ▼
  Router  ─── classifies intent, selects agent, builds plan
     │              (OTel span: router.classify)
     ▼
 Executor  ─── dispatches to plugin/subagent
     │              (OTel span: executor.dispatch)
     │
     ├──► FileManager  (pure Python + OTel spans)
     ├──► WebSearch    (any framework + OTel spans)
     └──► Direct       (LLM direct handling)
     │
     ▼
Synthesizer  ─── shapes final response
     │              (OTel span: synthesizer.format)
     ▼
 AIMessage
```

### Why OpenTelemetry for step streaming?

Every agent emits raw OTel spans tagged with `max.run_id`. A custom `SpanProcessor` 
routes `span.on_end()` calls into per-run `asyncio.Queue`s. FastAPI SSEs those queues 
to the frontend. **No coupling to LangGraph internals** — any framework works.

```
Agent (any framework)
    │  span.set_attribute("max.run_id", run_id)
    ▼
MaxSpanProcessor.on_end()
    │  call_soon_threadsafe → asyncio.Queue
    ▼
FastAPI SSE /threads/{id}/runs/stream
    │
    ▼
Frontend Steps Panel (tree view via parent_id → span_id)
```

## Quickstart

### 1. Get a Groq API key
Sign up at [console.groq.com](https://console.groq.com) — it's free.

### 2. Backend

```bash
# From repo root
# Create and activate a virtualenv (example for Windows PowerShell)
python -m venv backend/.venv
backend/.venv\Scripts\Activate.ps1
pip install -e backend

# Add your key to backend/.env (create the file if missing)
echo "GROQ_API_KEY=your_key_here" >> backend/.env

# Start the FastAPI app
cd backend
uvicorn max.main:app --reload --port 8000
```

API will be at `http://localhost:8000`  
Docs at `http://localhost:8000/docs`



## Project Structure

```
.
├── backend/
│   ├── pyproject.toml
│   └── max/
│       ├── otel/
│       │   ├── processor.py    ← MaxSpanProcessor (the core novel piece)
│       │   └── setup.py        ← TracerProvider initialization
│       ├── agents/
│       │   ├── router.py       ← Intent classification + agent selection
│       │   ├── executor.py     ← Dispatch to subagents
│       │   ├── synthesizer.py  ← Final response shaping
│       │   └── file_manager.py ← FileManager subagent (pure Python + OTel)
│       ├── core/
│       │   ├── state.py        ← MaxState TypedDict
│       │   └── graph.py        ← LangGraph StateGraph compilation
│       ├── plugins/
│       │   ├── registry.py     ← Manifest-driven plugin registry
│       │   └── manifests/      ← JSON manifests per plugin
│       ├── api/
│       │   ├── threads.py      ← Thread CRUD
│       │   ├── runs.py         ← SSE streaming endpoint
│       │   └── plugins.py      ← Plugin toggle API
│       └── main.py             ← FastAPI app + lifespan

└── README.md
```

## Adding a New Agent

1. Create `backend/max/agents/my_agent.py`:

```python
from max.otel import get_tracer

tracer = get_tracer("max.agents.my_agent")

def run_my_agent(user_message: str, plan: str, run_id: str) -> str:
    with tracer.start_as_current_span("my_agent.run") as span:
        span.set_attribute("max.run_id", run_id)    # required
        span.set_attribute("max.agent", "my_agent")
        span.set_attribute("max.step", "Doing my thing")
        
        # ... your logic here (any framework) ...
        result = "done"
        
        span.set_attribute("max.result_preview", result[:200])
        return result
```

2. Add a manifest at `backend/max/plugins/manifests/my_agent.json`:

```json
{
  "id": "my_agent",
  "name": "My Agent",
  "type": "agent",
  "description": "What my agent does",
  "enabled": true,
  "capabilities": ["thing1", "thing2"],
  "framework": "python"
}
```

3. Wire it in `executor.py`:

```python
from .my_agent import run_my_agent

# In executor_node():
elif selected == "my_agent":
    result = run_my_agent(user_message, plan, run_id)
```

That's it. The router will automatically route to it, and spans will appear in 
the frontend Steps Panel tree.

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /threads | Create thread |
| GET | /threads | List threads |
| GET | /threads/:id | Get thread |
| DELETE | /threads/:id | Delete thread |
| PATCH | /threads/:id | Rename thread |
| POST | /threads/:id/runs/stream | **SSE streaming run** |
| GET | /plugins | List plugins |
| PATCH | /plugins/:id/toggle | Enable/disable plugin |

### SSE Event Schema

```
data: {"type": "step", "span_id": "abc", "parent_id": null, "name": "router.classify", 
       "attrs": {"max.agent": "router", "max.step": "Classifying intent"}, 
       "status": "OK", "duration_ms": 142}

data: {"type": "result", "content": "The final response text..."}

data: [DONE]
```

## Tech Stack

**Backend:** FastAPI · LangGraph · LangChain-Groq · OpenTelemetry SDK · AsyncSqliteSaver  
**LLM:** Groq llama-3.3-70b-versatile
