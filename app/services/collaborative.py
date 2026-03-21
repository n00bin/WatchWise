"""
Internal collaborative filtering engine.

Builds recommendations from WatchWise users' own rating data.
Auto-scales weight based on how many active raters exist.

Thresholds:
  < 20 raters  → disabled (not enough data)
  20-100       → low weight (+3.0)
  100-1000     → medium weight (+5.0)
  1000+        → primary signal (+7.0)
"""

import math
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.media import Movie, TVShow


def _get_all_ratings(db: Session, model, id_field: str) -> dict:
    """Get all ratings as {user_id: {item_id: rating}}."""
    user_ratings = defaultdict(dict)
    items = db.query(model).filter(model.user_rating.isnot(None)).all()
    for item in items:
        item_id = getattr(item, id_field)
        user_ratings[item.user_id][item_id] = item.user_rating
    return user_ratings


def _cosine_similarity(ratings_a: dict, ratings_b: dict) -> float:
    """Cosine similarity between two users' rating vectors (shared items only)."""
    shared = set(ratings_a.keys()) & set(ratings_b.keys())
    if len(shared) < 3:
        return 0.0

    dot = sum(ratings_a[k] * ratings_b[k] for k in shared)
    mag_a = math.sqrt(sum(v ** 2 for k, v in ratings_a.items() if k in shared))
    mag_b = math.sqrt(sum(v ** 2 for k, v in ratings_b.items() if k in shared))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


def get_cf_weight(db: Session) -> float:
    """Determine CF weight based on number of active raters."""
    rater_ids = set()

    for movie in db.query(Movie.user_id).filter(Movie.user_rating.isnot(None)).distinct().all():
        rater_ids.add(movie[0])

    for show in db.query(TVShow.user_id).filter(TVShow.user_rating.isnot(None)).distinct().all():
        rater_ids.add(show[0])

    count = len(rater_ids)

    if count < 20:
        return 0.0
    elif count < 100:
        return 3.0
    elif count < 1000:
        return 5.0
    else:
        return 7.0


def get_cf_movie_recs(db: Session, user_id: int, limit: int = 30) -> list:
    """Get movie recommendations from internal collaborative filtering.

    Returns list of {tmdb_id, cf_score, supporter_count} for movies
    that similar users loved but this user hasn't seen.
    """
    weight = get_cf_weight(db)
    if weight == 0:
        return []

    all_ratings = _get_all_ratings(db, Movie, "tmdb_id")

    if user_id not in all_ratings:
        return []

    my_ratings = all_ratings[user_id]
    if len(my_ratings) < 3:
        return []

    # Find similar users
    similarities = {}
    for other_id, other_ratings in all_ratings.items():
        if other_id == user_id:
            continue
        sim = _cosine_similarity(my_ratings, other_ratings)
        if sim > 0.3:
            similarities[other_id] = sim

    if not similarities:
        return []

    # Collect recommendations from similar users
    candidates = defaultdict(lambda: {"weighted_score": 0, "supporters": 0})

    for other_id, sim in similarities.items():
        other_ratings = all_ratings[other_id]
        for tmdb_id, rating in other_ratings.items():
            if tmdb_id in my_ratings:
                continue
            if rating >= 4:
                candidates[tmdb_id]["weighted_score"] += sim * rating
                candidates[tmdb_id]["supporters"] += 1

    # Score and sort
    results = []
    for tmdb_id, data in candidates.items():
        if data["supporters"] < 2:
            continue
        results.append({
            "tmdb_id": tmdb_id,
            "cf_score": round(data["weighted_score"], 2),
            "supporter_count": data["supporters"],
            "cf_weight": weight,
        })

    results.sort(key=lambda x: x["cf_score"], reverse=True)
    return results[:limit]


def get_cf_tv_recs(db: Session, user_id: int, limit: int = 30) -> list:
    """Get TV show recommendations from internal collaborative filtering."""
    weight = get_cf_weight(db)
    if weight == 0:
        return []

    all_ratings = _get_all_ratings(db, TVShow, "tmdb_id")

    if user_id not in all_ratings:
        return []

    my_ratings = all_ratings[user_id]
    if len(my_ratings) < 3:
        return []

    similarities = {}
    for other_id, other_ratings in all_ratings.items():
        if other_id == user_id:
            continue
        sim = _cosine_similarity(my_ratings, other_ratings)
        if sim > 0.3:
            similarities[other_id] = sim

    if not similarities:
        return []

    candidates = defaultdict(lambda: {"weighted_score": 0, "supporters": 0})

    for other_id, sim in similarities.items():
        other_ratings = all_ratings[other_id]
        for tmdb_id, rating in other_ratings.items():
            if tmdb_id in my_ratings:
                continue
            if rating >= 4:
                candidates[tmdb_id]["weighted_score"] += sim * rating
                candidates[tmdb_id]["supporters"] += 1

    results = []
    for tmdb_id, data in candidates.items():
        if data["supporters"] < 2:
            continue
        results.append({
            "tmdb_id": tmdb_id,
            "cf_score": round(data["weighted_score"], 2),
            "supporter_count": data["supporters"],
            "cf_weight": weight,
        })

    results.sort(key=lambda x: x["cf_score"], reverse=True)
    return results[:limit]
