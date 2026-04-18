"""Persist the Google API key in a project-local .env file via python-dotenv."""

from pathlib import Path

from dotenv import dotenv_values, set_key, unset_key

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
KEY_NAME = "GOOGLE_API_KEY"


def load_api_key() -> str:
    if not ENV_PATH.exists():
        return ""
    return (dotenv_values(ENV_PATH).get(KEY_NAME) or "").strip()


def save_api_key(api_key: str) -> None:
    ENV_PATH.touch(exist_ok=True)
    set_key(str(ENV_PATH), KEY_NAME, api_key, quote_mode="always")


def clear_api_key() -> None:
    if ENV_PATH.exists():
        unset_key(str(ENV_PATH), KEY_NAME)
