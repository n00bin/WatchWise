import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import DATABASE_URL, DATA_DIR

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_db():
    """Migrate existing database to multi-tenant schema."""
    db_path = DATA_DIR / "watchwise.db"
    if not db_path.exists():
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # ── Phase 1: Add keywords_json and credits_json (existing migration) ──
    for table in ["movies", "tvshows"]:
        for col, default in [("keywords_json", "'[]'"), ("credits_json", "'{}'")]:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT DEFAULT {default}")
            except sqlite3.OperationalError:
                pass

    # ── Phase 2: Multi-tenant migration ──

    # Check if migration already done
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_exists = cursor.fetchone() is not None

    cursor.execute("PRAGMA table_info(movies)")
    movie_cols = [row[1] for row in cursor.fetchall()]
    has_user_id = "user_id" in movie_cols

    if has_user_id:
        # Migration already complete
        conn.commit()
        conn.close()
        return

    # Create users table
    if not users_exists:
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")

    # Seed default user (owns all existing data)
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        from app.services.auth import hash_password
        cursor.execute(
            "INSERT INTO users (id, username, email, password_hash, created_at) VALUES (1, ?, ?, ?, datetime('now'))",
            ("admin", "admin@watchwise.local", hash_password("watchwise")),
        )

    # Recreate media tables with user_id + compound unique constraint
    cursor.execute("PRAGMA foreign_keys = OFF")

    # ── Movies ──
    cursor.execute("ALTER TABLE movies RENAME TO _movies_old")
    cursor.execute("""
        CREATE TABLE movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
            tmdb_id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            overview TEXT DEFAULT '',
            poster_path VARCHAR(500) DEFAULT '',
            backdrop_path VARCHAR(500) DEFAULT '',
            release_date VARCHAR(20) DEFAULT '',
            runtime INTEGER DEFAULT 0,
            tmdb_rating REAL DEFAULT 0.0,
            status VARCHAR(20) DEFAULT 'watchlist',
            user_rating INTEGER,
            notes TEXT DEFAULT '',
            date_added DATETIME,
            date_watched DATETIME,
            keywords_json TEXT DEFAULT '[]',
            credits_json TEXT DEFAULT '{}',
            UNIQUE(user_id, tmdb_id)
        )
    """)
    cursor.execute("""
        INSERT INTO movies (id, user_id, tmdb_id, title, overview, poster_path, backdrop_path,
            release_date, runtime, tmdb_rating, status, user_rating, notes, date_added,
            date_watched, keywords_json, credits_json)
        SELECT id, 1, tmdb_id, title, overview, poster_path, backdrop_path,
            release_date, runtime, tmdb_rating, status, user_rating, notes, date_added,
            date_watched, keywords_json, credits_json
        FROM _movies_old
    """)
    cursor.execute("DROP TABLE _movies_old")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_movies_user_id ON movies(user_id)")

    # ── TV Shows ──
    cursor.execute("ALTER TABLE tvshows RENAME TO _tvshows_old")
    cursor.execute("""
        CREATE TABLE tvshows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
            tmdb_id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            overview TEXT DEFAULT '',
            poster_path VARCHAR(500) DEFAULT '',
            backdrop_path VARCHAR(500) DEFAULT '',
            first_air_date VARCHAR(20) DEFAULT '',
            number_of_seasons INTEGER DEFAULT 0,
            number_of_episodes INTEGER DEFAULT 0,
            episode_runtime INTEGER DEFAULT 0,
            tmdb_rating REAL DEFAULT 0.0,
            status VARCHAR(20) DEFAULT 'watchlist',
            user_rating INTEGER,
            notes TEXT DEFAULT '',
            date_added DATETIME,
            date_watched DATETIME,
            keywords_json TEXT DEFAULT '[]',
            credits_json TEXT DEFAULT '{}',
            UNIQUE(user_id, tmdb_id)
        )
    """)
    cursor.execute("""
        INSERT INTO tvshows (id, user_id, tmdb_id, title, overview, poster_path, backdrop_path,
            first_air_date, number_of_seasons, number_of_episodes, episode_runtime, tmdb_rating,
            status, user_rating, notes, date_added, date_watched, keywords_json, credits_json)
        SELECT id, 1, tmdb_id, title, overview, poster_path, backdrop_path,
            first_air_date, number_of_seasons, number_of_episodes, episode_runtime, tmdb_rating,
            status, user_rating, notes, date_added, date_watched, keywords_json, credits_json
        FROM _tvshows_old
    """)
    cursor.execute("DROP TABLE _tvshows_old")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_tvshows_user_id ON tvshows(user_id)")

    # ── Anime ──
    cursor.execute("ALTER TABLE anime RENAME TO _anime_old")
    cursor.execute("""
        CREATE TABLE anime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
            mal_id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            title_english VARCHAR(500) DEFAULT '',
            synopsis TEXT DEFAULT '',
            poster_url VARCHAR(500) DEFAULT '',
            mal_score REAL DEFAULT 0.0,
            episodes INTEGER DEFAULT 0,
            anime_type VARCHAR(20) DEFAULT '',
            source VARCHAR(50) DEFAULT '',
            airing_status VARCHAR(30) DEFAULT '',
            year INTEGER DEFAULT 0,
            season VARCHAR(20) DEFAULT '',
            studios_json TEXT DEFAULT '[]',
            genres_json TEXT DEFAULT '[]',
            themes_json TEXT DEFAULT '[]',
            status VARCHAR(20) DEFAULT 'plan_to_watch',
            user_rating INTEGER,
            current_episode INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            date_added DATETIME,
            date_watched DATETIME,
            UNIQUE(user_id, mal_id)
        )
    """)
    cursor.execute("""
        INSERT INTO anime (id, user_id, mal_id, title, title_english, synopsis, poster_url,
            mal_score, episodes, anime_type, source, airing_status, year, season,
            studios_json, genres_json, themes_json, status, user_rating, current_episode,
            notes, date_added, date_watched)
        SELECT id, 1, mal_id, title, title_english, synopsis, poster_url,
            mal_score, episodes, anime_type, source, airing_status, year, season,
            studios_json, genres_json, themes_json, status, user_rating, current_episode,
            notes, date_added, date_watched
        FROM _anime_old
    """)
    cursor.execute("DROP TABLE _anime_old")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_anime_user_id ON anime(user_id)")

    cursor.execute("PRAGMA foreign_keys = ON")

    conn.commit()
    conn.close()


def init_db():
    _migrate_db()
    # Import models so create_all knows about them
    from app.models import user, media  # noqa: F401
    Base.metadata.create_all(bind=engine)
