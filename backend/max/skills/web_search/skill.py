"""
max/skills/web_search/skill.py

Web Search skill — placeholder demonstrating the skill pattern.
Replace with a real search integration (e.g. SerpAPI, Tavily, DuckDuckGo).
"""

import logging

from max.otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("max.skills.web_search")


async def run(message: str, plan: str, run_id: str) -> str:
    """
    Entry point for the Web Search skill.
    Signature: async (message, plan, run_id) -> str
    """
    with tracer.start_as_current_span("web_search.run") as span:
        span.set_attribute("max.run_id", run_id)
        span.set_attribute("max.agent", "web_search")
        span.set_attribute("max.step", "Performing web search")
        span.set_attribute("max.query", message[:200])

        # TODO: integrate a real search provider (Tavily, SerpAPI, etc.)
        # Example with Tavily:
        #   from tavily import TavilyClient
        #   client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        #   results = client.search(query=message)
        #   return format_results(results)

        result = (
            f"[Web Search — placeholder] Query: '{message}'\n"
            "To enable real web search, integrate a search provider in "
            "max/skills/web_search/skill.py and set the required API key."
        )
        span.set_attribute("max.result_preview", result[:200])
        return result
