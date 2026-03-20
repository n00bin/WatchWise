"""TasteDive API wrapper for collaborative filtering recommendations."""

import re
import httpx
from app.config import TASTEDIVE_BASE_URL
from app.services.settings import get_tastedive_key


def _clean_title(title: str) -> str:
    """Clean a title for TasteDive search.
    TasteDive uses commas as separators and colons as type prefixes,
    so both must be stripped from titles."""
    # Take main title before colon (removes subtitles)
    if ": " in title:
        title = title.split(": ")[0]
    # Remove commas (TasteDive uses commas as query separators)
    title = title.replace(",", "")
    # Remove colons that survived
    title = title.replace(":", "")
    # Remove parenthetical info
    title = re.sub(r'\s*\(.*?\)\s*', ' ', title)
    return title.strip()


async def get_similar(titles: list, media_type: str = "movie", limit: int = 20) -> list:
    """Get collaborative filtering recommendations from TasteDive.

    Args:
        titles: List of movie/show titles the user likes
        media_type: "movie" or "show"
        limit: Max results to return

    Returns:
        List of dicts with {name, type, description}
    """
    key = get_tastedive_key()
    if not key or not titles:
        return []

    cleaned = [_clean_title(t) for t in titles[:5]]
    query = ", ".join(cleaned)

    params = {
        "q": query,
        "type": media_type,
        "limit": limit,
        "info": 1,
        "k": key,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                TASTEDIVE_BASE_URL,
                params=params,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        # TasteDive may use capitalized keys depending on API version
        similar = data.get("similar", data.get("Similar", {}))
        raw_results = similar.get("results", similar.get("Results", []))

        results = []
        for item in raw_results:
            name = item.get("name", item.get("Name", ""))
            results.append({
                "name": name,
                "type": item.get("type", item.get("Type", "")).lower(),
                "description": item.get("wTeaser", ""),
            })
        return results

    except Exception:
        return []


async def get_movie_recs(titles: list, limit: int = 20) -> list:
    """Get movie recommendations based on liked movie titles."""
    return await get_similar(titles, media_type="movie", limit=limit)


async def get_tv_recs(titles: list, limit: int = 20) -> list:
    """Get TV show recommendations based on liked show titles."""
    return await get_similar(titles, media_type="show", limit=limit)
