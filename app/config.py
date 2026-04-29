import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Use PostgreSQL if DATABASE_URL env var is set (production), otherwise SQLite (local dev)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'bingewatcher.db'}")
# Render uses "postgres://" but SQLAlchemy needs "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
JIKAN_BASE_URL = "https://api.jikan.moe/v4"
TASTEDIVE_BASE_URL = "https://tastedive.com/api/similar"
TRAKT_BASE_URL = "https://api.trakt.tv"

# Settings stored in a simple JSON file (local dev) or env vars (production)
SETTINGS_FILE = DATA_DIR / "settings.json"
