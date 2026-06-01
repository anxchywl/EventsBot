from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SUPPORTED_LANGUAGES = {"en", "ru", "kz"}
DEFAULT_LANGUAGE = "en"

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locales"


@lru_cache(maxsize=1)
def _load_catalogs() -> dict[str, dict[str, str]]:
    catalogs: dict[str, dict[str, str]] = {}
    for language in SUPPORTED_LANGUAGES:
        path = _LOCALE_DIR / f"{language}.json"
        with path.open("r", encoding="utf-8") as file:
            catalogs[language] = json.load(file)
    return catalogs


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return language
    return DEFAULT_LANGUAGE


def t(key: str, language: str | None = None, **kwargs: Any) -> str:
    lang = normalize_language(language)
    catalogs = _load_catalogs()
    text = catalogs.get(lang, {}).get(key)
    if text is None:
        text = catalogs[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


def user_language(user: Any | None) -> str:
    return normalize_language(getattr(user, "language", None))
