import json
import os
from app.config import SETTINGS_FILE

DEFAULT_SETTINGS = {
    "tmdb_api_key": "",
    "tastedive_api_key": "",
    "trakt_client_id": "",
    "server_port": 8500,
}


def load_settings() -> dict:
    # In production, use env vars
    env_settings = {}
    for key in DEFAULT_SETTINGS:
        env_val = os.environ.get(key.upper())
        if env_val:
            env_settings[key] = env_val

    if env_settings:
        return {**DEFAULT_SETTINGS, **env_settings}

    # Local dev: read from JSON file
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        return {**DEFAULT_SETTINGS, **saved}
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
