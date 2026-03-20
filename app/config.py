import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'watchwise.db'}"

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
JIKAN_BASE_URL = "https://api.jikan.moe/v4"
TASTEDIVE_BASE_URL = "https://tastedive.com/api/similar"
TRAKT_BASE_URL = "https://api.trakt.tv"

# Settings stored in a simple JSON file
SETTINGS_FILE = DATA_DIR / "settings.json"
