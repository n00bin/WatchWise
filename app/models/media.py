from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Table, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.database import Base

# Association tables
movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id"), primary_key=True),
)

tvshow_genres = Table(
    "tvshow_genres",
    Base.metadata,
    Column("tvshow_id", Integer, ForeignKey("tvshows.id"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id"), primary_key=True),
)


class DismissedRec(Base):
    __tablename__ = "dismissed_recs"
    __table_args__ = (
        UniqueConstraint("user_id", "media_type", "external_id", name="uq_dismissed_user_media"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    media_type = Column(String(10), nullable=False)  # movie, tv, anime
    external_id = Column(Integer, nullable=False)  # tmdb_id or mal_id
    created_at = Column(DateTime, default=datetime.utcnow)


class Genre(Base):
    __tablename__ = "genres"

    id = Column(Integer, primary_key=True)  # TMDB genre ID
    name = Column(String(100), nullable=False)


class Movie(Base):
    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint("user_id", "tmdb_id", name="uq_movie_user_tmdb"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1, index=True)
    tmdb_id = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    overview = Column(Text, default="")
    poster_path = Column(String(500), default="")
    backdrop_path = Column(String(500), default="")
    release_date = Column(String(20), default="")
    runtime = Column(Integer, default=0)
    tmdb_rating = Column(Float, default=0.0)

    # User data
    status = Column(String(20), default="watchlist")
    user_rating = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    date_added = Column(DateTime, default=datetime.utcnow)
    date_watched = Column(DateTime, nullable=True)

    # Enhanced metadata
    keywords_json = Column(Text, default="[]")
    credits_json = Column(Text, default="{}")

    genres = relationship("Genre", secondary=movie_genres, lazy="joined")


class TVShow(Base):
    __tablename__ = "tvshows"
    __table_args__ = (
        UniqueConstraint("user_id", "tmdb_id", name="uq_tvshow_user_tmdb"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1, index=True)
    tmdb_id = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    overview = Column(Text, default="")
    poster_path = Column(String(500), default="")
    backdrop_path = Column(String(500), default="")
    first_air_date = Column(String(20), default="")
    number_of_seasons = Column(Integer, default=0)
    number_of_episodes = Column(Integer, default=0)
    episode_runtime = Column(Integer, default=0)
    tmdb_rating = Column(Float, default=0.0)
    airing_status = Column(String(30), default="")  # Returning Series, Ended, Canceled

    # User data
    status = Column(String(20), default="watchlist")
    user_rating = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    date_added = Column(DateTime, default=datetime.utcnow)
    date_watched = Column(DateTime, nullable=True)

    # Enhanced metadata
    keywords_json = Column(Text, default="[]")
    credits_json = Column(Text, default="{}")

    genres = relationship("Genre", secondary=tvshow_genres, lazy="joined")


class Anime(Base):
    __tablename__ = "anime"
    __table_args__ = (
        UniqueConstraint("user_id", "mal_id", name="uq_anime_user_mal"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1, index=True)
    mal_id = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    title_english = Column(String(500), default="")
    synopsis = Column(Text, default="")
    poster_url = Column(String(500), default="")
    mal_score = Column(Float, default=0.0)
    episodes = Column(Integer, default=0)
    anime_type = Column(String(20), default="")
    source = Column(String(50), default="")
    airing_status = Column(String(30), default="")
    year = Column(Integer, default=0)
    season = Column(String(20), default="")
    studios_json = Column(Text, default="[]")
    genres_json = Column(Text, default="[]")
    themes_json = Column(Text, default="[]")

    # User data
    status = Column(String(20), default="plan_to_watch")
    user_rating = Column(Integer, nullable=True)
    current_episode = Column(Integer, default=0)
    notes = Column(Text, default="")
    date_added = Column(DateTime, default=datetime.utcnow)
    date_watched = Column(DateTime, nullable=True)
