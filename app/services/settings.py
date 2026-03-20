import json
from app.config import SETTINGS_FILE

DEFAULT_SETTINGS = {
    "tmdb_api_key": "",
    "tastedive_api_key": "",
    "trakt_client_id": "",
    "server_port": 8500,
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        # Merge with defaults for any new keys
        merged = {**DEFAULT_SETTINGS, **saved}
        return merged
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get_tmdb_key() -> str:
    return load_settings().get("tmdb_api_key", "")


def get_tastedive_key() -> str:
    return load_settings().get("tastedive_api_key", "")


def get_trakt_client_id() -> str:
    return load_settings().get("trakt_client_id", "")
