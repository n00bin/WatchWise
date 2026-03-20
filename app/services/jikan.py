"""Jikan API wrapper for MyAnimeList data (v4)."""

import asyncio
import httpx
from app.config import JIKAN_BASE_URL


async def _get(path: str, params: dict = None) -> dict:
    """Make a GET request to Jikan API with rate-limit retry."""
    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            resp = await client.get(
                f"{JIKAN_BASE_URL}{path}",
                params=params or {},
                timeout=15.0,
            )
            if resp.status_code == 429:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
    return {}


async def search_anime(query: str, page: int = 1) -> dict:
    """Search anime by title."""
    return await _get("/anime", {
        "q": query,
        "page": page,
        "sfw": "true",
        "limit": 15,
    })


async def get_anime_details(mal_id: int) -> dict:
    """Get full anime details."""
    data = await _get(f"/anime/{mal_id}/full")
    return data.get("data", {})


async def get_anime_recommendations(mal_id: int) -> list:
    """Get recommendations for an anime."""
    data = await _get(f"/anime/{mal_id}/recommendations")
    return data.get("data", [])


async def get_top_anime(page: int = 1, filter_type: str = "") -> dict:
    """Get top anime list."""
    params = {"page": page, "limit": 20}
    if filter_type:
        params["filter"] = filter_type  # airing, upcoming, bypopularity, favorite
    return await _get("/top/anime", params)


async def get_anime_by_genre(genre_ids: list, page: int = 1) -> dict:
    """Discover anime by genre IDs (MAL genre IDs)."""
    return await _get("/anime", {
        "genres": ",".join(str(g) for g in genre_ids),
        "order_by": "score",
        "sort": "desc",
        "min_score": 6,
        "sfw": "true",
        "page": page,
        "limit": 20,
    })
