"""
services/search_agent.py — Multi-Platform Search Agent Wrapper
===============================================================
Delegates crawling to ai_crawl_tool for unified pipeline execution.
"""

from typing import List, Dict, Any, Optional
from services.ai_crawl_tool import crawl_livestreams_with_ai


def search_livestreams(
    goal: str,
    limit: int = 20,
    use_headless: bool = False,
    platforms: Optional[List[str]] = None,
    platform_limits: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Backward-compatible wrapper around crawl_livestreams_with_ai.
    """
    res = crawl_livestreams_with_ai(
        goal,
        limit=limit,
        platforms=platforms,
        mode="fallback_only",
        use_headless=use_headless,
        cache=True,
    )
    return {
        "queries": res.get("queries", [goal]),
        "analysis": res.get("analysis", {}),
        "events": res.get("events", []),
    }