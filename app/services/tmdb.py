"""TMDB API wrapper — metadata, search, and image URLs.

Used for: searching titles, fetching details (with keywords/credits),
and generating poster/backdrop URLs. Recommendation endpoints removed
in v5 (handled by TasteDive + Trakt instead).
"""

import httpx
from app.config import TMDB_BASE_URL, TMDB_IMAGE_BASE
from app.services.settings import get_tmdb_key


def _headers():
    key = get_tmdb_key()
    return {"Authorization": f"Bearer {key}"} if key.startswith("ey") else {}


def _params():
    key = get_tmdb_key()
    if not key:
        return {}
    if key.startswith("ey"):
        return {}
    return {"api_key": key}


async def search_movies(query: str, page: int = 1) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE_URL}/search/movie",
            params={**_params(), "query": query, "page": page},
            headers=_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def search_tv(query: str, page: int = 1) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE_URL}/search/tv",
            params={**_params(), "query": query, "page": page},
            headers=_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def get_movie_details(tmdb_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE_URL}/movie/{tmdb_id}",
            params={**_params(), "append_to_response": "keywords,credits"},
            headers=_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def get_tv_details(tmdb_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE_URL}/tv/{tmdb_id}",
            params={**_params(), "append_to_response": "keywords,credits"},
            headers=_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def get_tv_simple(tmdb_id: int) -> dict:
    """Get TV show with next/last episode info (lighter than full details)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE_URL}/tv/{tmdb_id}",
            params=_params(),
            headers=_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def get_genre_list(media_type: str = "movie") -> list:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE_URL}/genre/{media_type}/list",
            params=_params(),
            headers=_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("genres", [])


def extract_keywords(details: dict) -> list:
    """Extract keywords from details response (with append_to_response)."""
    kw = details.get("keywords", {})
    return kw.get("keywords", kw.get("results", []))


def extract_credits(details: dict) -> dict:
    """Extract top cast and director from details response."""
    credits = details.get("credits", {})
    cast = [
        {"id": p["id"], "name": p["name"]}
        for p in credits.get("cast", [])[:5]
    ]
    directors = [
        {"id": p["id"], "name": p["name"]}
        for p in credits.get("crew", [])
        if p.get("job") == "Director"
    ]
    created_by = details.get("created_by", [])
    if created_by and not directors:
        directors = [{"id": p["id"], "name": p["name"]} for p in created_by[:2]]

    return {"cast": cast, "directors": directors}


def poster_url(path: str, size: str = "w342") -> str:
    if not path:
        return ""
    return f"{TMDB_IMAGE_BASE}/{size}{path}"


def backdrop_url(path: str, size: str = "w780") -> str:
    if not path:
        return ""
    return f"{TMDB_IMAGE_BASE}/{size}{path}"
