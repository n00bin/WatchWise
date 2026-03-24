"""
Smart recommendation engine v5.

Simplified for quality over complexity. Two real data sources + taste scoring.

Sources:
- TasteDive: collaborative filtering ("people who liked X also liked Y")
- Trakt: community-curated related content (real user lists)
- Genre/keyword affinity: scores candidates against user's taste profile

Removed (v4 bloat that didn't improve quality):
- TMDB direct recommendations/similar (popularity-biased)
- Two-hop page 2 fetching
- Person/actor discovery via TMDB discover
- Trending fusion
- Genre discover filler
- Cross-media anime <-> movies/TV bridging
- Popularity penalty hack
"""

import json
import random
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.media import Movie, TVShow, Anime
from app.services import tmdb, jikan, tastedive, trakt, collaborative


# ─── Profile Building ────────────────────────────────────────────────


def _recency_multiplier(date_watched) -> float:
    """Boost recent ratings. Returns 1.0-1.5 based on how recent."""
    if not date_watched:
        return 1.0
    days_ago = (datetime.utcnow() - date_watched).days
    if days_ago < 30:
        return 1.5
    elif days_ago < 90:
        return 1.3
    elif days_ago < 180:
        return 1.15
    return 1.0


def _build_genre_profile(db: Session, user_id: int) -> dict:
    """Build genre affinity from ALL ratings with recency weighting."""
    genre_data = defaultdict(lambda: {"name": "", "ratings": []})

    for movie in db.query(Movie).filter(Movie.user_id == user_id, Movie.user_rating.isnot(None)).all():
        recency = _recency_multiplier(movie.date_watched)
        for g in movie.genres:
            genre_data[g.id]["name"] = g.name
            genre_data[g.id]["ratings"].append(movie.user_rating * recency)

    for show in db.query(TVShow).filter(TVShow.user_id == user_id, TVShow.user_rating.isnot(None)).all():
        recency = _recency_multiplier(show.date_watched)
        for g in show.genres:
            genre_data[g.id]["name"] = g.name
            genre_data[g.id]["ratings"].append(show.user_rating * recency)

    # Dropped items count as strong negative signal
    for movie in db.query(Movie).filter(Movie.user_id == user_id, Movie.status == "dropped", Movie.user_rating.is_(None)).all():
        for g in movie.genres:
            genre_data[g.id]["name"] = g.name
            genre_data[g.id]["ratings"].append(0.5)

    for show in db.query(TVShow).filter(TVShow.user_id == user_id, TVShow.status == "dropped", TVShow.user_rating.is_(None)).all():
        for g in show.genres:
            genre_data[g.id]["name"] = g.name
            genre_data[g.id]["ratings"].append(0.5)

    # Items rated 1-2 stars get extra negative weight
    for movie in db.query(Movie).filter(Movie.user_id == user_id, Movie.user_rating <= 2, Movie.user_rating.isnot(None)).all():
        for g in movie.genres:
            genre_data[g.id]["ratings"].append(movie.user_rating * 0.8)

    for show in db.query(TVShow).filter(TVShow.user_id == user_id, TVShow.user_rating <= 2, TVShow.user_rating.isnot(None)).all():
        for g in show.genres:
            genre_data[g.id]["ratings"].append(show.user_rating * 0.8)

    profile = {}
    for gid, data in genre_data.items():
        if not data["ratings"]:
            continue
        avg = sum(data["ratings"]) / len(data["ratings"])
        affinity = (avg - 3.0)
        confidence = min(len(data["ratings"]) / 3.0, 2.0)
        profile[gid] = {
            "name": data["name"],
            "affinity": affinity * confidence,
            "avg_rating": avg,
            "count": len(data["ratings"]),
        }

    return profile


def _build_keyword_profile(db: Session, user_id: int) -> dict:
    """Build keyword affinity from rated movies/shows with stored keywords."""
    kw_data = defaultdict(lambda: {"name": "", "ratings": []})

    for movie in db.query(Movie).filter(Movie.user_id == user_id, Movie.user_rating.isnot(None)).all():
        try:
            keywords = json.loads(movie.keywords_json) if movie.keywords_json else []
        except (json.JSONDecodeError, TypeError):
            keywords = []
        recency = _recency_multiplier(movie.date_watched)
        for kw in keywords:
            kid = kw.get("id", 0)
            kw_data[kid]["name"] = kw.get("name", "")
            kw_data[kid]["ratings"].append(movie.user_rating * recency)

    for show in db.query(TVShow).filter(TVShow.user_id == user_id, TVShow.user_rating.isnot(None)).all():
        try:
            keywords = json.loads(show.keywords_json) if show.keywords_json else []
        except (json.JSONDecodeError, TypeError):
            keywords = []
        recency = _recency_multiplier(show.date_watched)
        for kw in keywords:
            kid = kw.get("id", 0)
            kw_data[kid]["name"] = kw.get("name", "")
            kw_data[kid]["ratings"].append(show.user_rating * recency)

    profile = {}
    for kid, data in kw_data.items():
        if not data["ratings"] or not kid:
            continue
        avg = sum(data["ratings"]) / len(data["ratings"])
        affinity = (avg - 3.0)
        confidence = min(len(data["ratings"]) / 2.0, 1.5)
        profile[kid] = {
            "name": data["name"],
            "affinity": affinity * confidence,
        }

    return profile


# ─── Scoring ─────────────────────────────────────────────────────────


def _score_candidate(
    item: dict,
    candidate: dict,
    genre_profile: dict,
    keyword_profile: dict = None,
    shuffle: bool = False,
) -> float:
    """Score a candidate using source signal + taste profile."""

    # Base quality from TMDB rating
    tmdb_rating = item.get("vote_average", 0)
    base_score = tmdb_rating / 10.0

    # Source scoring
    source_score = 0

    if candidate.get("tastedive"):
        source_score += 6.5

    if candidate.get("trakt"):
        source_score += 5.5

    # Internal collaborative filtering (auto-scales with user base)
    if candidate.get("cf_weight"):
        source_score += candidate["cf_weight"]

    # Frequency boost (recommended by multiple sources = stronger signal)
    freq = candidate["frequency"]
    source_score += freq * 0.5

    # Genre affinity
    genre_ids = item.get("genre_ids", [])
    genre_score = 0
    genre_penalty = 0
    for gid in genre_ids:
        if gid in genre_profile:
            affinity = genre_profile[gid]["affinity"]
            if affinity > 0:
                genre_score += affinity * 0.5
            elif affinity < -0.5:
                genre_penalty += abs(affinity) * 1.5

    # Keyword affinity bonus
    keyword_score = candidate.get("keyword_bonus", 0)

    # Shuffle mode
    if shuffle:
        variety = random.uniform(0, 8.0)
    else:
        variety = random.uniform(0, 0.2)

    total = base_score + source_score + genre_score - genre_penalty + keyword_score + variety
    return max(total, 0)


# ─── Collection Helpers ──────────────────────────────────────────────


async def _collect_tastedive_recs(loved_items, tracked_ids, candidates, search_fn, td_fn, media_type):
    """TasteDive collaborative filtering.
    Sends loved titles, gets 'people who liked X also liked Y' results,
    then looks them up on TMDB for metadata."""

    if not loved_items:
        return

    all_titles = [item.title for item in loved_items]
    td_results = []
    seen = set()

    # Send loved titles in batches of 5 (up to 50 titles = 10 API calls)
    for i in range(0, min(len(all_titles), 50), 5):
        batch = all_titles[i:i+5]
        if not batch:
            break
        batch_results = await td_fn(batch, limit=20)
        for r in batch_results:
            if r["name"].lower() not in seen:
                td_results.append(r)
                seen.add(r["name"].lower())

    if not td_results:
        return

    for td_item in td_results:
        title = td_item["name"]
        try:
            data = await search_fn(title)
            tmdb_results = data.get("results", [])
            if not tmdb_results:
                continue

            best = tmdb_results[0]
            tid = best["id"]
            if tid in tracked_ids:
                continue

            c = candidates[tid]
            if c["data"] is None:
                c["data"] = best
                c["media_type"] = media_type
                c["tastedive"] = True
            if "Fans also liked" not in c["sources"]:
                c["sources"].insert(0, "Fans also liked")
                c["frequency"] += 4
        except Exception:
            continue


async def _collect_trakt_recs(loved_items, tracked_ids, candidates, fetch_related, search_fn, media_type):
    """Trakt community-driven related content.
    Uses Trakt's /related endpoint curated by real user lists,
    then looks up results on TMDB for metadata/posters."""

    if not loved_items:
        return

    for item in loved_items[:50]:
        try:
            related = await fetch_related(tmdb_id=item.tmdb_id, limit=10)
            for rel in related:
                rel_tmdb_id = rel.get("tmdb_id")
                if not rel_tmdb_id or rel_tmdb_id in tracked_ids:
                    continue

                c = candidates[rel_tmdb_id]
                if c["data"] is None:
                    try:
                        search_data = await search_fn(rel["title"])
                        tmdb_results = search_data.get("results", [])
                        if not tmdb_results:
                            continue
                        best = None
                        for sr in tmdb_results:
                            if sr["id"] == rel_tmdb_id:
                                best = sr
                                break
                        if not best:
                            best = tmdb_results[0]
                        c["data"] = best
                        c["media_type"] = media_type
                        c["trakt"] = True
                    except Exception:
                        continue

                label = f"Related to {item.title}"
                if label not in c["sources"]:
                    c["sources"].append(label)
                    c["frequency"] += 3
        except Exception:
            continue


# ─── Movie Recommendations ──────────────────────────────────────────


async def get_movie_recommendations(db: Session, user_id: int, limit: int = 100, shuffle: bool = False) -> list:
    genre_profile = _build_genre_profile(db, user_id)
    keyword_profile = _build_keyword_profile(db, user_id)

    loved_movies = (
        db.query(Movie)
        .filter(Movie.user_id == user_id, Movie.user_rating >= 4, Movie.status == "watched")
        .order_by(Movie.user_rating.desc())
        .all()
    )
    if not loved_movies:
        loved_movies = (
            db.query(Movie)
            .filter(Movie.user_id == user_id, Movie.status == "watched", Movie.user_rating.isnot(None))
            .order_by(Movie.user_rating.desc())
            .limit(10)
            .all()
        )

    if not loved_movies and not genre_profile:
        return []

    tracked_ids = {m.tmdb_id for m in db.query(Movie).filter(Movie.user_id == user_id).all()}

    candidates = defaultdict(lambda: {
        "data": None,
        "sources": [],
        "frequency": 0,
        "weighted_score": 0,
        "media_type": "movie",
        "tastedive": False,
        "trakt": False,
        "cf_weight": 0,
        "keyword_bonus": 0,
    })

    # Internal CF: WatchWise community (auto-activates with enough users)
    cf_recs = collaborative.get_cf_movie_recs(db, user_id)
    for cf in cf_recs:
        tid = cf["tmdb_id"]
        if tid in tracked_ids:
            continue
        c = candidates[tid]
        c["cf_weight"] = cf["cf_weight"]
        if "WatchWise community" not in c["sources"]:
            c["sources"].insert(0, "WatchWise community")
            c["frequency"] += cf["supporter_count"]
        # Look up on TMDB if we don't have data yet
        if c["data"] is None:
            try:
                search_data = await tmdb.search_movies(str(tid))
                for sr in search_data.get("results", []):
                    if sr["id"] == tid:
                        c["data"] = sr
                        c["media_type"] = "movie"
                        break
            except Exception:
                pass

    # TasteDive: collaborative filtering
    if loved_movies:
        await _collect_tastedive_recs(
            loved_movies, tracked_ids, candidates,
            tmdb.search_movies, tastedive.get_movie_recs,
            "movie"
        )

    # Trakt: community-driven related content
    if loved_movies:
        await _collect_trakt_recs(
            loved_movies, tracked_ids, candidates,
            trakt.get_related_movies, tmdb.search_movies,
            "movie"
        )

    # Score and sort
    scored = []
    for tid, c in candidates.items():
        item = c["data"]
        if not item:
            continue
        score = _score_candidate(item, c, genre_profile, keyword_profile, shuffle)
        title = item.get("title") or item.get("name", "")
        date_field = item.get("release_date") or item.get("first_air_date", "")

        scored.append({
            "tmdb_id": tid,
            "title": title,
            "overview": item.get("overview", ""),
            "poster_path": item.get("poster_path", ""),
            "release_date": date_field,
            "first_air_date": "",
            "tmdb_rating": item.get("vote_average", 0),
            "score": round(score, 2),
            "because": c["sources"][:3],
            "media_type": "movie",
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


# ─── TV Show Recommendations ────────────────────────────────────────


async def get_tv_recommendations(db: Session, user_id: int, limit: int = 100, shuffle: bool = False) -> list:
    genre_profile = _build_genre_profile(db, user_id)
    keyword_profile = _build_keyword_profile(db, user_id)

    loved_shows = (
        db.query(TVShow)
        .filter(TVShow.user_id == user_id, TVShow.user_rating >= 4, TVShow.status == "watched")
        .order_by(TVShow.user_rating.desc())
        .all()
    )
    if not loved_shows:
        loved_shows = (
            db.query(TVShow)
            .filter(TVShow.user_id == user_id, TVShow.status == "watched", TVShow.user_rating.isnot(None))
            .order_by(TVShow.user_rating.desc())
            .limit(10)
            .all()
        )

    if not loved_shows and not genre_profile:
        return []

    tracked_ids = {s.tmdb_id for s in db.query(TVShow).filter(TVShow.user_id == user_id).all()}

    candidates = defaultdict(lambda: {
        "data": None,
        "sources": [],
        "frequency": 0,
        "weighted_score": 0,
        "media_type": "tv",
        "tastedive": False,
        "trakt": False,
        "cf_weight": 0,
        "keyword_bonus": 0,
    })

    # Internal CF: WatchWise community
    cf_recs = collaborative.get_cf_tv_recs(db, user_id)
    for cf in cf_recs:
        tid = cf["tmdb_id"]
        if tid in tracked_ids:
            continue
        c = candidates[tid]
        c["cf_weight"] = cf["cf_weight"]
        if "WatchWise community" not in c["sources"]:
            c["sources"].insert(0, "WatchWise community")
            c["frequency"] += cf["supporter_count"]
        if c["data"] is None:
            try:
                search_data = await tmdb.search_tv(str(tid))
                for sr in search_data.get("results", []):
                    if sr["id"] == tid:
                        c["data"] = sr
                        c["media_type"] = "tv"
                        break
            except Exception:
                pass

    # TasteDive: collaborative filtering
    if loved_shows:
        await _collect_tastedive_recs(
            loved_shows, tracked_ids, candidates,
            tmdb.search_tv, tastedive.get_tv_recs,
            "tv"
        )

    # Trakt: community-driven related content
    if loved_shows:
        await _collect_trakt_recs(
            loved_shows, tracked_ids, candidates,
            trakt.get_related_shows, tmdb.search_tv,
            "tv"
        )

    # Score and sort
    scored = []
    for tid, c in candidates.items():
        item = c["data"]
        if not item:
            continue
        score = _score_candidate(item, c, genre_profile, keyword_profile, shuffle)
        title = item.get("title") or item.get("name", "")
        date_field = item.get("release_date") or item.get("first_air_date", "")

        scored.append({
            "tmdb_id": tid,
            "title": title,
            "overview": item.get("overview", ""),
            "poster_path": item.get("poster_path", ""),
            "release_date": "",
            "first_air_date": date_field,
            "tmdb_rating": item.get("vote_average", 0),
            "score": round(score, 2),
            "because": c["sources"][:3],
            "media_type": "tv",
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


# ─── Anime Recommendations ──────────────────────────────────────────


def _build_anime_genre_profile(db: Session, user_id: int) -> dict:
    """Build genre affinity from anime ratings."""
    genre_data = defaultdict(lambda: {"ratings": []})

    for anime in db.query(Anime).filter(Anime.user_id == user_id, Anime.user_rating.isnot(None)).all():
        try:
            genres = json.loads(anime.genres_json) if anime.genres_json else []
        except (json.JSONDecodeError, TypeError):
            genres = []
        recency = _recency_multiplier(anime.date_watched)
        for g in genres:
            genre_data[g]["ratings"].append(anime.user_rating * recency)

    for anime in db.query(Anime).filter(Anime.user_id == user_id, Anime.status == "dropped", Anime.user_rating.is_(None)).all():
        try:
            genres = json.loads(anime.genres_json) if anime.genres_json else []
        except (json.JSONDecodeError, TypeError):
            genres = []
        for g in genres:
            genre_data[g]["ratings"].append(0.5)

    profile = {}
    for name, data in genre_data.items():
        if not data["ratings"]:
            continue
        avg = sum(data["ratings"]) / len(data["ratings"])
        affinity = (avg - 3.0)
        confidence = min(len(data["ratings"]) / 3.0, 2.0)
        profile[name] = {
            "affinity": affinity * confidence,
            "avg_rating": avg,
            "count": len(data["ratings"]),
        }

    return profile


async def get_anime_recommendations(db: Session, user_id: int, limit: int = 100, shuffle: bool = False) -> list:
    """Generate anime recommendations from Jikan API."""
    loved_anime = (
        db.query(Anime)
        .filter(Anime.user_id == user_id, Anime.user_rating >= 4, Anime.status == "completed")
        .order_by(Anime.user_rating.desc())
        .all()
    )
    if not loved_anime:
        loved_anime = (
            db.query(Anime)
            .filter(Anime.user_id == user_id, Anime.status == "completed", Anime.user_rating.isnot(None))
            .order_by(Anime.user_rating.desc())
            .limit(10)
            .all()
        )

    if not loved_anime:
        return []

    tracked_ids = {a.mal_id for a in db.query(Anime).filter(Anime.user_id == user_id).all()}

    candidates = {}

    for anime in loved_anime[:6]:
        try:
            recs = await jikan.get_anime_recommendations(anime.mal_id)
            for rec in recs[:10]:
                entry = rec.get("entry", {})
                mal_id = entry.get("mal_id", 0)
                if not mal_id or mal_id in tracked_ids:
                    continue
                if mal_id not in candidates:
                    candidates[mal_id] = {
                        "data": entry,
                        "sources": [],
                        "frequency": 0,
                        "weighted_score": 0,
                    }
                c = candidates[mal_id]
                if anime.title not in c["sources"]:
                    c["sources"].append(anime.title)
                    c["frequency"] += 1
                    c["weighted_score"] += anime.user_rating
        except Exception:
            continue

    scored = []
    for mal_id, c in candidates.items():
        entry = c["data"]
        if not entry:
            continue

        # Fetch full details to get English title if missing
        title_english = entry.get("title_english", "")
        if not title_english:
            try:
                full = await jikan.get_anime_details(mal_id)
                title_english = full.get("title_english", "") or ""
                # Also grab better images/synopsis if available
                if full.get("images"):
                    entry["images"] = full["images"]
                if full.get("synopsis"):
                    entry["synopsis"] = full["synopsis"]
            except Exception:
                pass

        images = entry.get("images", {}).get("jpg", {})
        poster = images.get("image_url", "")

        freq = c["frequency"]
        base = freq * 2.0
        if freq > 0:
            avg_source = c["weighted_score"] / freq
            base += avg_source * 0.8

        if shuffle:
            base += random.uniform(0, 6.0)
        else:
            base += random.uniform(0, 0.2)

        scored.append({
            "mal_id": mal_id,
            "title": entry.get("title", ""),
            "title_english": title_english,
            "synopsis": (entry.get("synopsis") or entry.get("title", ""))[:200],
            "poster_url": poster,
            "mal_score": entry.get("score", 0) or 0,
            "episodes": entry.get("episodes", 0) or 0,
            "score": round(base, 2),
            "because": c["sources"][:3],
            "media_type": "anime",
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
