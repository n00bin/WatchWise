"""Trakt API wrapper for community-driven related content recommendations."""

import httpx
from app.config import TRAKT_BASE_URL
from app.services.settings import get_trakt_client_id


def _headers():
    client_id = get_trakt_client_id()
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id,
    }


async def _lookup_trakt_slug(tmdb_id: int, media_type: str = "movie") -> str:
    """Look up a Trakt slug from a TMDB ID. Required because Trakt's numeric IDs
    differ from TMDB's — passing a raw TMDB ID returns wrong results."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TRAKT_BASE_URL}/search/tmdb/{tmdb_id}",
                params={"type": media_type},
                headers=_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        if data:
            item = data[0].get(media_type, {})
            return item.get("ids", {}).get("slug", "")
    except Exception:
        pass
    return ""


async def get_related_movies(tmdb_id: int = None, limit: int = 10) -> list:
    """Get community-driven related movies from Trakt.

    Looks up the Trakt slug from the TMDB ID first, then fetches related content.

    Returns:
        List of dicts with {title, year, tmdb_id, imdb_id, trakt_slug}
    """
    if not get_trakt_client_id() or not tmdb_id:
        return []

    slug = await _lookup_trakt_slug(tmdb_id, "movie")
    if not slug:
        return []

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TRAKT_BASE_URL}/movies/{slug}/related",
                params={"page": 1, "limit": limit, "extended": "full"},
                headers=_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            results = resp.json()

        return [
            {
                "title": item.get("title", ""),
                "year": item.get("year"),
                "tmdb_id": item.get("ids", {}).get("tmdb"),
                "imdb_id": item.get("ids", {}).get("imdb"),
                "trakt_slug": item.get("ids", {}).get("slug"),
                "trakt_rating": item.get("rating", 0),
                "trakt_votes": item.get("votes", 0),
            }
            for item in results
            if item.get("ids", {}).get("tmdb")
        ]

    except Exception:
        return []


async def get_related_shows(tmdb_id: int = None, limit: int = 10) -> list:
    """Get community-driven related TV shows from Trakt."""
    if not get_trakt_client_id() or not tmdb_id:
        return []

    slug = await _lookup_trakt_slug(tmdb_id, "show")
    if not slug:
        return []

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TRAKT_BASE_URL}/shows/{slug}/related",
                params={"page": 1, "limit": limit, "extended": "full"},
                headers=_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            results = resp.json()

        return [
            {
                "title": item.get("title", ""),
                "year": item.get("year"),
                "tmdb_id": item.get("ids", {}).get("tmdb"),
                "imdb_id": item.get("ids", {}).get("imdb"),
                "trakt_slug": item.get("ids", {}).get("slug"),
                "trakt_rating": item.get("rating", 0),
                "trakt_votes": item.get("votes", 0),
            }
            for item in results
            if item.get("ids", {}).get("tmdb")
        ]

    except Exception:
        return []
