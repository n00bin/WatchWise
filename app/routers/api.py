import csv
import io
import json
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.media import Movie, TVShow, Genre, Anime, movie_genres, tvshow_genres
from app.models.feedback import Feedback, FeedbackVote
from app.models.user import User
from app.services import tmdb, jikan
from app.services import recommendations as rec_service
from app.services.auth import get_current_user, require_admin

router = APIRouter(prefix="/api")


# ─── Search ──────────────────────────────────────────────────────────

@router.get("/search")
async def search(q: str = Query(...), media_type: str = Query("movie"), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        if media_type == "anime":
            tracked_ids = {a.mal_id for a in db.query(Anime).filter(Anime.user_id == user.id).all()}
            data = await jikan.search_anime(q)
            results = []
            for item in data.get("data", [])[:15]:
                mal_id = item["mal_id"]
                if mal_id in tracked_ids:
                    continue
                images = item.get("images", {}).get("jpg", {})
                results.append({
                    "mal_id": mal_id,
                    "title": item.get("title", ""),
                    "title_english": item.get("title_english", ""),
                    "overview": (item.get("synopsis") or "")[:200],
                    "poster_path": images.get("small_image_url", ""),
                    "release_date": str(item.get("year", "") or ""),
                    "tmdb_rating": item.get("score", 0) or 0,
                    "episodes": item.get("episodes", 0) or 0,
                    "anime_type": item.get("type", ""),
                    "media_type": "anime",
                })
            return results

        if media_type == "movie":
            tracked_ids = {m.tmdb_id for m in db.query(Movie).filter(Movie.user_id == user.id).all()}
            data = await tmdb.search_movies(q)
        else:
            tracked_ids = {s.tmdb_id for s in db.query(TVShow).filter(TVShow.user_id == user.id).all()}
            data = await tmdb.search_tv(q)

        results = []
        for item in data.get("results", [])[:15]:
            tmdb_id = item["id"]
            if tmdb_id in tracked_ids:
                continue
            results.append({
                "tmdb_id": tmdb_id,
                "title": item.get("title") or item.get("name", ""),
                "overview": item.get("overview", "")[:200],
                "poster_path": tmdb.poster_url(item.get("poster_path", ""), "w185"),
                "release_date": item.get("release_date") or item.get("first_air_date", ""),
                "tmdb_rating": item.get("vote_average", 0),
                "media_type": media_type,
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Movies ──────────────────────────────────────────────────────────

def _ensure_genres(db: Session, genre_list: list) -> list:
    genres = []
    for g in genre_list:
        existing = db.query(Genre).filter(Genre.id == g["id"]).first()
        if not existing:
            existing = Genre(id=g["id"], name=g["name"])
            db.add(existing)
            db.flush()
        genres.append(existing)
    return genres


@router.post("/movies")
async def add_movie(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tmdb_id = data.get("tmdb_id")
    if not tmdb_id:
        raise HTTPException(status_code=400, detail="tmdb_id required")

    existing = db.query(Movie).filter(Movie.user_id == user.id, Movie.tmdb_id == tmdb_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Movie already tracked")

    details = await tmdb.get_movie_details(tmdb_id)
    genres = _ensure_genres(db, details.get("genres", []))
    keywords = tmdb.extract_keywords(details)
    credits = tmdb.extract_credits(details)

    movie = Movie(
        user_id=user.id,
        tmdb_id=tmdb_id,
        title=details.get("title", ""),
        overview=details.get("overview", ""),
        poster_path=details.get("poster_path", ""),
        backdrop_path=details.get("backdrop_path", ""),
        release_date=details.get("release_date", ""),
        runtime=details.get("runtime", 0),
        tmdb_rating=details.get("vote_average", 0),
        status=data.get("status", "watchlist"),
        keywords_json=json.dumps(keywords),
        credits_json=json.dumps(credits),
    )
    movie.genres = genres

    if data.get("user_rating"):
        movie.user_rating = data["user_rating"]

    if movie.status == "watched":
        movie.date_watched = datetime.utcnow()

    db.add(movie)
    db.commit()
    return {"status": "ok", "id": movie.id, "title": movie.title}


@router.get("/movies")
async def get_movies(
    status: str = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Movie).filter(Movie.user_id == user.id)
    if status:
        query = query.filter(Movie.status == status)
    movies = query.order_by(Movie.date_added.desc()).all()

    return [
        {
            "id": m.id,
            "tmdb_id": m.tmdb_id,
            "title": m.title,
            "overview": m.overview[:200] if m.overview else "",
            "poster_path": tmdb.poster_url(m.poster_path),
            "release_date": m.release_date,
            "runtime": m.runtime,
            "tmdb_rating": m.tmdb_rating,
            "status": m.status,
            "user_rating": m.user_rating,
            "notes": m.notes,
            "date_added": m.date_added.isoformat() if m.date_added else "",
            "date_watched": m.date_watched.isoformat() if m.date_watched else "",
            "genres": [g.name for g in m.genres],
        }
        for m in movies
    ]


@router.put("/movies/{movie_id}")
async def update_movie(movie_id: int, data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    movie = db.query(Movie).filter(Movie.id == movie_id, Movie.user_id == user.id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    if "status" in data:
        old_status = movie.status
        movie.status = data["status"]
        if data["status"] == "watched" and old_status != "watched":
            movie.date_watched = datetime.utcnow()

    if "user_rating" in data:
        movie.user_rating = data["user_rating"]

    if "notes" in data:
        movie.notes = data["notes"]

    db.commit()
    return {"status": "ok"}


@router.delete("/movies/{movie_id}")
async def delete_movie(movie_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    movie = db.query(Movie).filter(Movie.id == movie_id, Movie.user_id == user.id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    db.delete(movie)
    db.commit()
    return {"status": "ok"}


# ─── TV Shows ────────────────────────────────────────────────────────

@router.post("/tvshows")
async def add_tvshow(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tmdb_id = data.get("tmdb_id")
    if not tmdb_id:
        raise HTTPException(status_code=400, detail="tmdb_id required")

    existing = db.query(TVShow).filter(TVShow.user_id == user.id, TVShow.tmdb_id == tmdb_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="TV show already tracked")

    details = await tmdb.get_tv_details(tmdb_id)
    genres = _ensure_genres(db, details.get("genres", []))
    keywords = tmdb.extract_keywords(details)
    credits = tmdb.extract_credits(details)
    runtimes = details.get("episode_run_time", [])
    avg_runtime = runtimes[0] if runtimes else 0

    show = TVShow(
        user_id=user.id,
        tmdb_id=tmdb_id,
        title=details.get("name", ""),
        overview=details.get("overview", ""),
        poster_path=details.get("poster_path", ""),
        backdrop_path=details.get("backdrop_path", ""),
        first_air_date=details.get("first_air_date", ""),
        number_of_seasons=details.get("number_of_seasons", 0),
        number_of_episodes=details.get("number_of_episodes", 0),
        episode_runtime=avg_runtime,
        tmdb_rating=details.get("vote_average", 0),
        airing_status=details.get("status", "") or "",
        status=data.get("status", "watchlist"),
        keywords_json=json.dumps(keywords),
        credits_json=json.dumps(credits),
    )
    show.genres = genres

    if data.get("user_rating"):
        show.user_rating = data["user_rating"]

    if show.status == "watched":
        show.date_watched = datetime.utcnow()

    db.add(show)
    db.commit()
    return {"status": "ok", "id": show.id, "title": show.title}


@router.get("/tvshows")
async def get_tvshows(
    status: str = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(TVShow).filter(TVShow.user_id == user.id)
    if status:
        query = query.filter(TVShow.status == status)
    shows = query.order_by(TVShow.date_added.desc()).all()

    return [
        {
            "id": s.id,
            "tmdb_id": s.tmdb_id,
            "title": s.title,
            "overview": s.overview[:200] if s.overview else "",
            "poster_path": tmdb.poster_url(s.poster_path),
            "first_air_date": s.first_air_date,
            "number_of_seasons": s.number_of_seasons,
            "number_of_episodes": s.number_of_episodes,
            "episode_runtime": s.episode_runtime,
            "tmdb_rating": s.tmdb_rating,
            "airing_status": s.airing_status or "",
            "status": s.status,
            "user_rating": s.user_rating,
            "notes": s.notes,
            "date_added": s.date_added.isoformat() if s.date_added else "",
            "date_watched": s.date_watched.isoformat() if s.date_watched else "",
            "genres": [g.name for g in s.genres],
        }
        for s in shows
    ]


@router.put("/tvshows/{show_id}")
async def update_tvshow(show_id: int, data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    show = db.query(TVShow).filter(TVShow.id == show_id, TVShow.user_id == user.id).first()
    if not show:
        raise HTTPException(status_code=404, detail="TV show not found")

    if "status" in data:
        old_status = show.status
        show.status = data["status"]
        if data["status"] == "watched" and old_status != "watched":
            show.date_watched = datetime.utcnow()

    if "user_rating" in data:
        show.user_rating = data["user_rating"]

    if "notes" in data:
        show.notes = data["notes"]

    db.commit()
    return {"status": "ok"}


@router.delete("/tvshows/{show_id}")
async def delete_tvshow(show_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    show = db.query(TVShow).filter(TVShow.id == show_id, TVShow.user_id == user.id).first()
    if not show:
        raise HTTPException(status_code=404, detail="TV show not found")
    db.delete(show)
    db.commit()
    return {"status": "ok"}


# ─── Anime ───────────────────────────────────────────────────────────

@router.post("/anime")
async def add_anime(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mal_id = data.get("mal_id")
    if not mal_id:
        raise HTTPException(status_code=400, detail="mal_id required")

    existing = db.query(Anime).filter(Anime.user_id == user.id, Anime.mal_id == mal_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Anime already tracked")

    details = await jikan.get_anime_details(mal_id)
    if not details:
        raise HTTPException(status_code=404, detail="Anime not found on MyAnimeList")

    images = details.get("images", {}).get("jpg", {})
    studios = [s.get("name", "") for s in details.get("studios", [])]
    genres = [g.get("name", "") for g in details.get("genres", [])]
    themes = [t.get("name", "") for t in details.get("themes", [])]

    anime = Anime(
        user_id=user.id,
        mal_id=mal_id,
        title=details.get("title", ""),
        title_english=details.get("title_english", "") or "",
        synopsis=details.get("synopsis", "") or "",
        poster_url=images.get("image_url", ""),
        mal_score=details.get("score", 0) or 0,
        episodes=details.get("episodes", 0) or 0,
        anime_type=details.get("type", "") or "",
        source=details.get("source", "") or "",
        airing_status=details.get("status", "") or "",
        year=details.get("year", 0) or 0,
        season=details.get("season", "") or "",
        studios_json=json.dumps(studios),
        genres_json=json.dumps(genres),
        themes_json=json.dumps(themes),
        status=data.get("status", "plan_to_watch"),
    )

    if data.get("user_rating"):
        anime.user_rating = data["user_rating"]

    if anime.status == "completed":
        anime.date_watched = datetime.utcnow()
        anime.current_episode = anime.episodes

    db.add(anime)
    db.commit()
    return {"status": "ok", "id": anime.id, "title": anime.title}


@router.get("/anime")
async def get_anime(
    status: str = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Anime).filter(Anime.user_id == user.id)
    if status:
        query = query.filter(Anime.status == status)
    anime_list = query.order_by(Anime.date_added.desc()).all()

    return [
        {
            "id": a.id,
            "mal_id": a.mal_id,
            "title": a.title,
            "title_english": a.title_english,
            "synopsis": (a.synopsis or "")[:200],
            "poster_url": a.poster_url,
            "mal_score": a.mal_score,
            "episodes": a.episodes,
            "anime_type": a.anime_type,
            "source": a.source,
            "airing_status": a.airing_status,
            "year": a.year,
            "season": a.season,
            "studios": json.loads(a.studios_json) if a.studios_json else [],
            "genres": json.loads(a.genres_json) if a.genres_json else [],
            "themes": json.loads(a.themes_json) if a.themes_json else [],
            "status": a.status,
            "user_rating": a.user_rating,
            "current_episode": a.current_episode,
            "notes": a.notes,
            "date_added": a.date_added.isoformat() if a.date_added else "",
            "date_watched": a.date_watched.isoformat() if a.date_watched else "",
        }
        for a in anime_list
    ]


@router.put("/anime/{anime_id}")
async def update_anime(anime_id: int, data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    anime = db.query(Anime).filter(Anime.id == anime_id, Anime.user_id == user.id).first()
    if not anime:
        raise HTTPException(status_code=404, detail="Anime not found")

    if "status" in data:
        old_status = anime.status
        anime.status = data["status"]
        if data["status"] == "completed" and old_status != "completed":
            anime.date_watched = datetime.utcnow()
            if anime.episodes:
                anime.current_episode = anime.episodes

    if "user_rating" in data:
        anime.user_rating = data["user_rating"]

    if "current_episode" in data:
        anime.current_episode = data["current_episode"]

    if "notes" in data:
        anime.notes = data["notes"]

    db.commit()
    return {"status": "ok"}


@router.delete("/anime/{anime_id}")
async def delete_anime(anime_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    anime = db.query(Anime).filter(Anime.id == anime_id, Anime.user_id == user.id).first()
    if not anime:
        raise HTTPException(status_code=404, detail="Anime not found")
    db.delete(anime)
    db.commit()
    return {"status": "ok"}


# ─── Dashboard Stats ─────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    movies = db.query(Movie).filter(Movie.user_id == user.id).all()
    tvshows = db.query(TVShow).filter(TVShow.user_id == user.id).all()
    anime_list = db.query(Anime).filter(Anime.user_id == user.id).all()

    watched_movies = [m for m in movies if m.status == "watched"]
    watched_shows = [s for s in tvshows if s.status == "watched"]
    completed_anime = [a for a in anime_list if a.status == "completed"]
    rated_movies = [m for m in watched_movies if m.user_rating]
    rated_shows = [s for s in watched_shows if s.user_rating]
    rated_anime = [a for a in completed_anime if a.user_rating]

    # Genre breakdowns — overall + per media type
    genre_counts = {}
    genre_ratings = {}
    movie_genre_counts = {}
    tv_genre_counts = {}
    anime_genre_counts = {}

    for item in watched_movies:
        for g in item.genres:
            genre_counts[g.name] = genre_counts.get(g.name, 0) + 1
            movie_genre_counts[g.name] = movie_genre_counts.get(g.name, 0) + 1
            if item.user_rating:
                if g.name not in genre_ratings:
                    genre_ratings[g.name] = []
                genre_ratings[g.name].append(item.user_rating)

    for item in watched_shows:
        for g in item.genres:
            genre_counts[g.name] = genre_counts.get(g.name, 0) + 1
            tv_genre_counts[g.name] = tv_genre_counts.get(g.name, 0) + 1
            if item.user_rating:
                if g.name not in genre_ratings:
                    genre_ratings[g.name] = []
                genre_ratings[g.name].append(item.user_rating)

    for a in completed_anime:
        try:
            genres = json.loads(a.genres_json) if a.genres_json else []
        except (json.JSONDecodeError, TypeError):
            genres = []
        try:
            themes = json.loads(a.themes_json) if a.themes_json else []
        except (json.JSONDecodeError, TypeError):
            themes = []
        for g in genres + themes:
            genre_counts[g] = genre_counts.get(g, 0) + 1
            anime_genre_counts[g] = anime_genre_counts.get(g, 0) + 1
            if a.user_rating:
                if g not in genre_ratings:
                    genre_ratings[g] = []
                genre_ratings[g].append(a.user_rating)

    genre_avg_ratings = {
        name: round(sum(ratings) / len(ratings), 1)
        for name, ratings in genre_ratings.items()
    }

    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for m in rated_movies:
        rating_dist[m.user_rating] = rating_dist.get(m.user_rating, 0) + 1
    for s in rated_shows:
        rating_dist[s.user_rating] = rating_dist.get(s.user_rating, 0) + 1
    for a in rated_anime:
        rating_dist[a.user_rating] = rating_dist.get(a.user_rating, 0) + 1

    monthly = {}
    for item in watched_movies + watched_shows + completed_anime:
        if item.date_watched:
            key = item.date_watched.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + 1

    movie_hours = sum(m.runtime or 0 for m in watched_movies) / 60
    tv_hours = sum(
        (s.number_of_episodes or 0) * (s.episode_runtime or 45)
        for s in watched_shows
    ) / 60
    anime_hours = sum(
        (a.episodes or 0) * 24
        for a in completed_anime
    ) / 60

    top_genres = sorted(
        genre_avg_ratings.items(), key=lambda x: x[1], reverse=True
    )[:5]

    movie_statuses = {}
    for m in movies:
        movie_statuses[m.status] = movie_statuses.get(m.status, 0) + 1
    tv_statuses = {}
    for s in tvshows:
        tv_statuses[s.status] = tv_statuses.get(s.status, 0) + 1
    anime_statuses = {}
    for a in anime_list:
        anime_statuses[a.status] = anime_statuses.get(a.status, 0) + 1

    return {
        "total_movies": len(movies),
        "total_tvshows": len(tvshows),
        "total_anime": len(anime_list),
        "watched_movies": len(watched_movies),
        "watched_tvshows": len(watched_shows),
        "completed_anime": len(completed_anime),
        "avg_movie_rating": round(
            sum(m.user_rating for m in rated_movies) / len(rated_movies), 1
        ) if rated_movies else 0,
        "avg_tvshow_rating": round(
            sum(s.user_rating for s in rated_shows) / len(rated_shows), 1
        ) if rated_shows else 0,
        "avg_anime_rating": round(
            sum(a.user_rating for a in rated_anime) / len(rated_anime), 1
        ) if rated_anime else 0,
        "genre_counts": dict(sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)),
        "movie_genre_counts": dict(sorted(movie_genre_counts.items(), key=lambda x: x[1], reverse=True)),
        "tv_genre_counts": dict(sorted(tv_genre_counts.items(), key=lambda x: x[1], reverse=True)),
        "anime_genre_counts": dict(sorted(anime_genre_counts.items(), key=lambda x: x[1], reverse=True)),
        "genre_avg_ratings": genre_avg_ratings,
        "rating_distribution": rating_dist,
        "monthly_watched": dict(sorted(monthly.items())),
        "movie_hours": round(movie_hours, 1),
        "tv_hours": round(tv_hours, 1),
        "anime_hours": round(anime_hours, 1),
        "total_hours": round(movie_hours + tv_hours + anime_hours, 1),
        "top_genres": top_genres,
        "movie_statuses": movie_statuses,
        "tv_statuses": tv_statuses,
        "anime_statuses": anime_statuses,
        "unrated_movies": len(watched_movies) - len(rated_movies),
        "unrated_tvshows": len(watched_shows) - len(rated_shows),
        "unrated_anime": len(completed_anime) - len(rated_anime),
    }


# ─── Trending on WatchWise ────────────────────────────────────────────

@router.get("/trending")
async def get_trending(db: Session = Depends(get_db)):
    """Global trending on WatchWise — most rated titles this week across all users."""
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Top rated movies this week (by number of ratings)
    trending_movies = (
        db.query(
            Movie.tmdb_id,
            Movie.title,
            Movie.poster_path,
            Movie.release_date,
            func.count(Movie.id).label("rating_count"),
            func.avg(Movie.user_rating).label("avg_rating"),
        )
        .filter(Movie.user_rating.isnot(None), Movie.date_watched >= week_ago)
        .group_by(Movie.tmdb_id)
        .order_by(func.count(Movie.id).desc())
        .limit(10)
        .all()
    )

    # Top rated TV shows this week
    trending_tv = (
        db.query(
            TVShow.tmdb_id,
            TVShow.title,
            TVShow.poster_path,
            TVShow.first_air_date,
            func.count(TVShow.id).label("rating_count"),
            func.avg(TVShow.user_rating).label("avg_rating"),
        )
        .filter(TVShow.user_rating.isnot(None), TVShow.date_watched >= week_ago)
        .group_by(TVShow.tmdb_id)
        .order_by(func.count(TVShow.id).desc())
        .limit(10)
        .all()
    )

    # Top rated anime this week
    trending_anime = (
        db.query(
            Anime.mal_id,
            Anime.title,
            Anime.title_english,
            Anime.poster_url,
            func.count(Anime.id).label("rating_count"),
            func.avg(Anime.user_rating).label("avg_rating"),
        )
        .filter(Anime.user_rating.isnot(None), Anime.date_watched >= week_ago)
        .group_by(Anime.mal_id)
        .order_by(func.count(Anime.id).desc())
        .limit(10)
        .all()
    )

    # If not enough this week, expand to all time
    if len(trending_movies) < 3:
        trending_movies = (
            db.query(
                Movie.tmdb_id,
                Movie.title,
                Movie.poster_path,
                Movie.release_date,
                func.count(Movie.id).label("rating_count"),
                func.avg(Movie.user_rating).label("avg_rating"),
            )
            .filter(Movie.user_rating.isnot(None))
            .group_by(Movie.tmdb_id)
            .order_by(func.count(Movie.id).desc())
            .limit(10)
            .all()
        )

    if len(trending_tv) < 3:
        trending_tv = (
            db.query(
                TVShow.tmdb_id,
                TVShow.title,
                TVShow.poster_path,
                TVShow.first_air_date,
                func.count(TVShow.id).label("rating_count"),
                func.avg(TVShow.user_rating).label("avg_rating"),
            )
            .filter(TVShow.user_rating.isnot(None))
            .group_by(TVShow.tmdb_id)
            .order_by(func.count(TVShow.id).desc())
            .limit(10)
            .all()
        )

    if len(trending_anime) < 3:
        trending_anime = (
            db.query(
                Anime.mal_id,
                Anime.title,
                Anime.title_english,
                Anime.poster_url,
                func.count(Anime.id).label("rating_count"),
                func.avg(Anime.user_rating).label("avg_rating"),
            )
            .filter(Anime.user_rating.isnot(None))
            .group_by(Anime.mal_id)
            .order_by(func.count(Anime.id).desc())
            .limit(10)
            .all()
        )

    return {
        "movies": [
            {
                "title": m.title,
                "poster_path": tmdb.poster_url(m.poster_path, "w185"),
                "year": (m.release_date or "")[:4],
                "rating_count": m.rating_count,
                "avg_rating": round(float(m.avg_rating), 1),
            }
            for m in trending_movies
        ],
        "tvshows": [
            {
                "title": s.title,
                "poster_path": tmdb.poster_url(s.poster_path, "w185"),
                "year": (s.first_air_date or "")[:4],
                "rating_count": s.rating_count,
                "avg_rating": round(float(s.avg_rating), 1),
            }
            for s in trending_tv
        ],
        "anime": [
            {
                "title": a.title_english or a.title,
                "poster_url": a.poster_url,
                "rating_count": a.rating_count,
                "avg_rating": round(float(a.avg_rating), 1),
            }
            for a in trending_anime
        ],
    }


# ─── Calendar ────────────────────────────────────────────────────────

@router.get("/calendar")
async def get_calendar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get upcoming episodes for shows the user is currently watching."""
    watching_shows = db.query(TVShow).filter(
        TVShow.user_id == user.id,
        TVShow.status == "watching"
    ).all()

    upcoming = []

    for show in watching_shows:
        try:
            data = await tmdb.get_tv_simple(show.tmdb_id)

            next_ep = data.get("next_episode_to_air")
            if next_ep and next_ep.get("air_date"):
                upcoming.append({
                    "show_title": show.title,
                    "poster_path": tmdb.poster_url(show.poster_path, "w185"),
                    "season": next_ep.get("season_number", 0),
                    "episode": next_ep.get("episode_number", 0),
                    "episode_name": next_ep.get("name", ""),
                    "air_date": next_ep["air_date"],
                    "overview": (next_ep.get("overview") or "")[:150],
                    "media_type": "tv",
                })

            # Also check if show is still airing
            status = data.get("status", "")
            last_ep = data.get("last_episode_to_air")
            if not next_ep and last_ep and status in ("Returning Series", "In Production"):
                upcoming.append({
                    "show_title": show.title,
                    "poster_path": tmdb.poster_url(show.poster_path, "w185"),
                    "season": last_ep.get("season_number", 0),
                    "episode": last_ep.get("episode_number", 0),
                    "episode_name": "Waiting for new episodes",
                    "air_date": "",
                    "overview": f"{status} — no air date announced yet",
                    "media_type": "tv",
                })
        except Exception:
            continue

    # Anime currently watching
    watching_anime = db.query(Anime).filter(
        Anime.user_id == user.id,
        Anime.status == "watching"
    ).all()

    for anime in watching_anime:
        try:
            data = await jikan.get_anime_details(anime.mal_id)
            status = data.get("status", "")
            broadcast = data.get("broadcast", {})
            aired = data.get("aired", {})

            if status == "Currently Airing":
                # Try to get next airing day from broadcast info
                day = broadcast.get("day", "")
                time_str = broadcast.get("time", "")
                air_info = f"Airs {day}" + (f" at {time_str} JST" if time_str else "")

                upcoming.append({
                    "show_title": anime.title_english or anime.title,
                    "poster_path": anime.poster_url,
                    "season": 1,
                    "episode": (anime.current_episode or 0) + 1,
                    "episode_name": air_info,
                    "air_date": "",  # Jikan doesn't give exact next episode date
                    "overview": f"Episode {(anime.current_episode or 0) + 1} of {anime.episodes or '?'} — Currently Airing",
                    "media_type": "anime",
                })
            elif status == "Not yet aired":
                air_from = aired.get("from", "")
                air_date = air_from[:10] if air_from else ""
                upcoming.append({
                    "show_title": anime.title_english or anime.title,
                    "poster_path": anime.poster_url,
                    "season": 1,
                    "episode": 1,
                    "episode_name": "Upcoming",
                    "air_date": air_date,
                    "overview": f"Premieres {air_date}" if air_date else "Air date TBA",
                    "media_type": "anime",
                })
        except Exception:
            continue

    # Sort by air date (items with dates first, then undated)
    upcoming.sort(key=lambda x: x["air_date"] if x["air_date"] else "9999-99-99")

    return {"upcoming": upcoming, "watching_count": len(watching_shows) + len(watching_anime)}


# ─── Recommendations ─────────────────────────────────────────────────

@router.get("/recommendations/movies")
async def get_movie_recs(
    page: int = Query(1, ge=1),
    shuffle: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        per_page = 20
        recs = await rec_service.get_movie_recommendations(
            db, user_id=user.id, limit=per_page * 3, shuffle=shuffle
        )
        total = len(recs)
        start = (page - 1) * per_page
        page_recs = recs[start:start + per_page]
        for r in page_recs:
            r["poster_path"] = tmdb.poster_url(r["poster_path"])
        return {
            "results": page_recs,
            "page": page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations/tvshows")
async def get_tv_recs(
    page: int = Query(1, ge=1),
    shuffle: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        per_page = 20
        recs = await rec_service.get_tv_recommendations(
            db, user_id=user.id, limit=per_page * 3, shuffle=shuffle
        )
        total = len(recs)
        start = (page - 1) * per_page
        page_recs = recs[start:start + per_page]
        for r in page_recs:
            r["poster_path"] = tmdb.poster_url(r["poster_path"])
        return {
            "results": page_recs,
            "page": page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations/anime")
async def get_anime_recs(
    page: int = Query(1, ge=1),
    shuffle: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        per_page = 20
        recs = await rec_service.get_anime_recommendations(
            db, user_id=user.id, limit=per_page * 3, shuffle=shuffle
        )
        total = len(recs)
        start = (page - 1) * per_page
        page_recs = recs[start:start + per_page]
        return {
            "results": page_recs,
            "page": page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Feedback ────────────────────────────────────────────────────────

@router.get("/feedback")
async def get_feedback(
    feedback_type: str = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all feedback, sorted by vote count. Optionally filter by type."""

    query = db.query(Feedback)
    if feedback_type:
        query = query.filter(Feedback.type == feedback_type)
    items = query.all()

    # Get vote counts and whether current user voted
    results = []
    for item in items:
        vote_count = db.query(FeedbackVote).filter(FeedbackVote.feedback_id == item.id).count()
        user_voted = db.query(FeedbackVote).filter(
            FeedbackVote.feedback_id == item.id,
            FeedbackVote.user_id == user.id,
        ).first() is not None

        results.append({
            "id": item.id,
            "type": item.type,
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "vote_count": vote_count,
            "user_voted": user_voted,
            "is_author": item.user_id == user.id,
            "created_at": item.created_at.isoformat() if item.created_at else "",
        })

    results.sort(key=lambda x: x["vote_count"], reverse=True)
    return results


@router.post("/feedback")
async def create_feedback(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    feedback_type = data.get("type", "").strip()
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()

    if feedback_type not in ("issue", "feature"):
        raise HTTPException(status_code=400, detail="Type must be 'issue' or 'feature'")
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    item = Feedback(
        user_id=user.id,
        type=feedback_type,
        title=title,
        description=description,
    )
    db.add(item)
    db.flush()

    # Auto-upvote your own submission
    vote = FeedbackVote(feedback_id=item.id, user_id=user.id)
    db.add(vote)
    db.commit()

    return {"status": "ok", "id": item.id}


@router.post("/feedback/{feedback_id}/vote")
async def toggle_vote(feedback_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")

    existing = db.query(FeedbackVote).filter(
        FeedbackVote.feedback_id == feedback_id,
        FeedbackVote.user_id == user.id,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"status": "ok", "voted": False}
    else:
        vote = FeedbackVote(feedback_id=feedback_id, user_id=user.id)
        db.add(vote)
        db.commit()
        return {"status": "ok", "voted": True}


# ─── Admin ───────────────────────────────────────────────────────────

@router.put("/feedback/{feedback_id}/status")
async def update_feedback_status(feedback_id: int, data: dict, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")

    status = data.get("status", "")
    if status not in ("open", "in_progress", "done", "closed"):
        raise HTTPException(status_code=400, detail="Invalid status")

    item.status = status
    db.commit()
    return {"status": "ok"}


@router.delete("/feedback/{feedback_id}")
async def delete_feedback(feedback_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")
    db.delete(item)
    db.commit()
    return {"status": "ok"}


@router.get("/admin/users")
async def get_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    results = []
    for u in users:
        movie_count = db.query(Movie).filter(Movie.user_id == u.id).count()
        tv_count = db.query(TVShow).filter(TVShow.user_id == u.id).count()
        anime_count = db.query(Anime).filter(Anime.user_id == u.id).count()
        rated_count = (
            db.query(Movie).filter(Movie.user_id == u.id, Movie.user_rating.isnot(None)).count() +
            db.query(TVShow).filter(TVShow.user_id == u.id, TVShow.user_rating.isnot(None)).count() +
            db.query(Anime).filter(Anime.user_id == u.id, Anime.user_rating.isnot(None)).count()
        )
        results.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_admin": bool(u.is_admin),
            "created_at": u.created_at.isoformat() if u.created_at else "",
            "total_items": movie_count + tv_count + anime_count,
            "rated_items": rated_count,
        })
    return results


# ─── Import ──────────────────────────────────────────────────────────

def _clean_title(raw: str) -> tuple:
    title = raw.strip()
    title = re.sub(r'\s*\[.*?\]\s*$', '', title)
    title = re.sub(r'\s*\(Trailer\)\s*$', '', title, flags=re.I)
    title = re.sub(r'\s*\(Bonus\)\s*$', '', title, flags=re.I)
    title = re.sub(r'\s*\(Behind the Scenes\)\s*$', '', title, flags=re.I)

    is_tv = False
    season_match = re.match(r'^(.+?)[\s:·\-]+\s*(?:Season|Series|S)\s*\d+', title, re.I)
    if season_match:
        title = season_match.group(1).strip()
        is_tv = True

    ep_match = re.match(r'^(.+?)[\s:·\-]+\s*(?:S\d+E\d+|Episode\s+\d+|Ep\.?\s*\d+)', title, re.I)
    if ep_match:
        title = ep_match.group(1).strip()
        is_tv = True

    title = title.rstrip(':').rstrip('-').rstrip('·').strip()
    return title, 'tv' if is_tv else 'movie'


@router.post("/import/parse-csv")
async def parse_import_csv(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await file.read()

    for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
        try:
            text = content.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise HTTPException(status_code=400, detail="Could not decode CSV file")

    reader = csv.DictReader(io.StringIO(text))

    title_col = None
    if reader.fieldnames:
        for col in reader.fieldnames:
            col_lower = col.lower().strip()
            if col_lower in ('title', 'video title', 'name', 'movie title', 'show title'):
                title_col = col
                break
        if not title_col:
            for col in reader.fieldnames:
                if 'title' in col.lower() or 'name' in col.lower():
                    title_col = col
                    break
        if not title_col and reader.fieldnames:
            title_col = reader.fieldnames[0]

    if not title_col:
        raise HTTPException(status_code=400, detail="Could not find a title column in the CSV")

    seen_titles = set()
    unique_titles = []

    for row in reader:
        raw = row.get(title_col, '').strip()
        if not raw:
            continue
        clean, media_type = _clean_title(raw)
        if clean.lower() not in seen_titles and len(clean) > 1:
            seen_titles.add(clean.lower())
            unique_titles.append({
                'original': raw,
                'clean': clean,
                'type_guess': media_type,
            })

    existing_movie_titles = {m.title.lower() for m in db.query(Movie).filter(Movie.user_id == user.id).all()}
    existing_tv_titles = {s.title.lower() for s in db.query(TVShow).filter(TVShow.user_id == user.id).all()}

    results = []
    for item in unique_titles[:100]:
        if item['clean'].lower() in existing_movie_titles or item['clean'].lower() in existing_tv_titles:
            results.append({
                'original': item['original'],
                'clean': item['clean'],
                'status': 'exists',
                'match': None,
            })
            continue

        try:
            if item['type_guess'] == 'tv':
                data = await tmdb.search_tv(item['clean'])
            else:
                data = await tmdb.search_movies(item['clean'])

            tmdb_results = data.get('results', [])
            if tmdb_results:
                best = tmdb_results[0]
                results.append({
                    'original': item['original'],
                    'clean': item['clean'],
                    'status': 'matched',
                    'match': {
                        'tmdb_id': best['id'],
                        'title': best.get('title') or best.get('name', ''),
                        'poster_path': tmdb.poster_url(best.get('poster_path', ''), 'w92'),
                        'release_date': best.get('release_date') or best.get('first_air_date', ''),
                        'tmdb_rating': best.get('vote_average', 0),
                        'media_type': item['type_guess'],
                    },
                })
            else:
                alt_type = 'movie' if item['type_guess'] == 'tv' else 'tv'
                if alt_type == 'tv':
                    data = await tmdb.search_tv(item['clean'])
                else:
                    data = await tmdb.search_movies(item['clean'])

                tmdb_results = data.get('results', [])
                if tmdb_results:
                    best = tmdb_results[0]
                    results.append({
                        'original': item['original'],
                        'clean': item['clean'],
                        'status': 'matched',
                        'match': {
                            'tmdb_id': best['id'],
                            'title': best.get('title') or best.get('name', ''),
                            'poster_path': tmdb.poster_url(best.get('poster_path', ''), 'w92'),
                            'release_date': best.get('release_date') or best.get('first_air_date', ''),
                            'tmdb_rating': best.get('vote_average', 0),
                            'media_type': alt_type,
                        },
                    })
                else:
                    results.append({
                        'original': item['original'],
                        'clean': item['clean'],
                        'status': 'not_found',
                        'match': None,
                    })
        except Exception:
            results.append({
                'original': item['original'],
                'clean': item['clean'],
                'status': 'not_found',
                'match': None,
            })

    return results


@router.post("/import/bulk-add")
async def bulk_import(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = data.get("items", [])
    added = 0
    skipped = 0

    for item in items:
        tmdb_id = item.get("tmdb_id")
        media_type = item.get("media_type", "movie")
        status = item.get("status", "watched")

        try:
            if media_type == "movie":
                existing = db.query(Movie).filter(Movie.user_id == user.id, Movie.tmdb_id == tmdb_id).first()
                if existing:
                    skipped += 1
                    continue

                details = await tmdb.get_movie_details(tmdb_id)
                genres = _ensure_genres(db, details.get("genres", []))
                keywords = tmdb.extract_keywords(details)
                credits = tmdb.extract_credits(details)

                movie = Movie(
                    user_id=user.id,
                    tmdb_id=tmdb_id,
                    title=details.get("title", ""),
                    overview=details.get("overview", ""),
                    poster_path=details.get("poster_path", ""),
                    backdrop_path=details.get("backdrop_path", ""),
                    release_date=details.get("release_date", ""),
                    runtime=details.get("runtime", 0),
                    tmdb_rating=details.get("vote_average", 0),
                    status=status,
                    keywords_json=json.dumps(keywords),
                    credits_json=json.dumps(credits),
                )
                movie.genres = genres
                if status == "watched":
                    movie.date_watched = datetime.utcnow()
                db.add(movie)
                added += 1
            else:
                existing = db.query(TVShow).filter(TVShow.user_id == user.id, TVShow.tmdb_id == tmdb_id).first()
                if existing:
                    skipped += 1
                    continue

                details = await tmdb.get_tv_details(tmdb_id)
                genres = _ensure_genres(db, details.get("genres", []))
                keywords = tmdb.extract_keywords(details)
                credits = tmdb.extract_credits(details)
                runtimes = details.get("episode_run_time", [])

                show = TVShow(
                    user_id=user.id,
                    tmdb_id=tmdb_id,
                    title=details.get("name", ""),
                    overview=details.get("overview", ""),
                    poster_path=details.get("poster_path", ""),
                    backdrop_path=details.get("backdrop_path", ""),
                    first_air_date=details.get("first_air_date", ""),
                    number_of_seasons=details.get("number_of_seasons", 0),
                    number_of_episodes=details.get("number_of_episodes", 0),
                    episode_runtime=runtimes[0] if runtimes else 0,
                    tmdb_rating=details.get("vote_average", 0),
                    airing_status=details.get("status", "") or "",
                    status=status,
                    keywords_json=json.dumps(keywords),
                    credits_json=json.dumps(credits),
                )
                show.genres = genres
                if status == "watched":
                    show.date_watched = datetime.utcnow()
                db.add(show)
                added += 1
        except Exception:
            skipped += 1
            continue

    db.commit()
    return {"added": added, "skipped": skipped}
