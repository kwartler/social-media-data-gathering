"""Local settings: API keys, the pseudonymization salt, the log, and caches.

These live in ~/.social_media_data_gathering/, which students never need to
open. Corpus zips are not kept here: like YT Timed Text, each one is handed to
the browser and lands in the Downloads folder. exports/ only holds them until
the browser has fetched them, and is emptied each time the app starts.
Keys can also come from environment variables, which override the saved file.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

HOME_DIR = Path.home() / ".social_media_data_gathering"
HOME_DIR.mkdir(exist_ok=True)

CONFIG_PATH = HOME_DIR / "config.json"
CACHE_DIR = HOME_DIR / "cache"
MEDIA_DIR = HOME_DIR / "media"
EXPORT_DIR = HOME_DIR / "exports"  # temporary; see module docstring
LOG_PATH = HOME_DIR / "collection_log.jsonl"
for d in (CACHE_DIR, MEDIA_DIR, EXPORT_DIR):
    d.mkdir(exist_ok=True)

DEFAULT_MODEL = "google/gemini-3.8-flash"

# Setting name -> environment variable that overrides it
ENV_OVERRIDES = {
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "reddit_client_id": "REDDIT_CLIENT_ID",
    "reddit_client_secret": "REDDIT_CLIENT_SECRET",
    "bluesky_handle": "BLUESKY_HANDLE",
    "bluesky_app_password": "BLUESKY_APP_PASSWORD",
}
SECRET_KEYS = {"openrouter_api_key", "reddit_client_secret", "bluesky_app_password"}


def _read() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def get(name: str, default: str = "") -> str:
    env = ENV_OVERRIDES.get(name)
    if env and os.environ.get(env):
        return os.environ[env]
    return _read().get(name) or default


def update(values: dict) -> None:
    """Save non-empty values. An explicit empty string clears a setting."""
    cfg = _read()
    for k, v in values.items():
        if v is None:
            continue
        if v == "":
            cfg.pop(k, None)
        else:
            cfg[k] = v
    _write(cfg)


def public_view() -> dict:
    """Settings safe to send to the browser: secrets become booleans."""
    out = {}
    for name in ENV_OVERRIDES:
        val = get(name)
        out[name] = bool(val) if name in SECRET_KEYS else val
    out["model"] = get("model", DEFAULT_MODEL)
    out["data_dir"] = str(HOME_DIR)
    return out


def clear_temp_exports() -> None:
    """Delete zips left from earlier sessions; the browser already saved them to Downloads."""
    for f in EXPORT_DIR.glob("*.zip"):
        f.unlink(missing_ok=True)


def salt() -> str:
    """Per-install random salt so pseudonyms can't be reversed by rehashing handles."""
    cfg = _read()
    if not cfg.get("salt"):
        cfg["salt"] = secrets.token_hex(16)
        _write(cfg)
    return cfg["salt"]
