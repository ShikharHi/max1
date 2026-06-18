---
id: web_search
name: Web Search
description: >
  Use this skill whenever the user wants to search the web, look up current
  information, check recent news, find facts, or retrieve content from a URL.
  Triggers include: "search for", "look up", "find online", "google", "web search",
  "latest news", "current information", "what is", "who is", "when did".
  Do NOT use for: file operations, calculations, or tasks that don't require
  external information retrieval.
triggers:
  - "search for"
  - "look up"
  - "find online"
  - "google"
  - "web search"
  - "latest news about"
  - "current information on"
  - "what is happening with"
  - "recent updates on"
  - "fetch url"
  - "read this page"
capabilities:
  - search_web
  - fetch_url
  - summarize_results
enabled: true
entry_point: skill.py
function: run
license: MIT
---

# Web Search Skill

## Purpose

This skill handles all queries that require retrieving current or external
information from the web. It bridges MAX with real-time data sources that the
base LLM does not have access to.

## When to Use

- User asks about current events, recent news, or time-sensitive facts
- User wants to look up information about a person, company, product, or topic
- User provides a URL and wants its content summarized or extracted
- User asks "what is the latest…", "search for…", "find me…"

## Execution

The skill has a Python runner (`skill.py::run`) that handles the actual search.
To enable real web search, integrate a search provider:

### Option A — Tavily (recommended)
```python
from tavily import TavilyClient
client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
results = client.search(query=message)
```

### Option B — SerpAPI
```python
import serpapi
results = serpapi.search(q=message, api_key=os.getenv("SERPAPI_KEY"))
```

### Option C — DuckDuckGo (no key required)
```python
from duckduckgo_search import DDGS
with DDGS() as ddgs:
    results = list(ddgs.text(message, max_results=5))
```

## Output Format

Return a concise, well-formatted markdown string containing:
1. A brief summary of the top result(s)
2. Key facts extracted from the search
3. Source URLs (when available)

## Resources

See `resources/references/` for provider documentation and rate-limit notes.
