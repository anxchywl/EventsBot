from __future__ import annotations

from urllib.parse import quote_plus
from urllib.parse import urlparse


def build_message_link(
    *,
    telegram_chat_id: int,
    message_id: int,
    username: str | None = None,
    chat_type: str | None = None,
) -> str | None:
    """Build a Telegram message URL only when Telegram supports one."""
    normalized_username = normalize_username(username)
    if normalized_username:
        return f"https://t.me/{normalized_username}/{message_id}"

    if chat_type not in {"supergroup", "channel"}:
        return None

    chat_id = str(telegram_chat_id)
    if not chat_id.startswith("-100"):
        return None

    internal_chat_id = chat_id[4:]
    if not internal_chat_id:
        return None

    return f"https://t.me/c/{internal_chat_id}/{message_id}"


def build_bot_start_link(*, bot_username: str | None, payload: str) -> str | None:
    normalized_username = normalize_username(bot_username)
    if not normalized_username:
        return None

    return f"https://t.me/{normalized_username}?start={payload}"


def build_event_deep_link(
    *, bot_username: str | None, public_token: str | None
) -> str | None:
    if not public_token:
        return None

    return build_bot_start_link(
        bot_username=bot_username,
        payload=f"event_{public_token}",
    )


def build_telegram_miniapp_direct_link(
    *,
    bot_username: str | None,
    miniapp_short_name: str | None,
    public_token: str | None,
) -> str | None:
    normalized_username = normalize_username(bot_username)
    normalized_short_name = normalize_username(miniapp_short_name)
    if not normalized_username or not normalized_short_name or not public_token:
        return None

    return (
        f"https://t.me/{normalized_username}/{normalized_short_name}"
        f"?startapp=event_{quote_plus(public_token)}"
    )


def build_telegram_miniapp_invite_link(
    *,
    bot_username: str | None,
    miniapp_short_name: str | None,
    token: str | None,
) -> str | None:
    normalized_username = normalize_username(bot_username)
    normalized_short_name = normalize_username(miniapp_short_name)
    if not normalized_username or not normalized_short_name or not token:
        return None

    return (
        f"https://t.me/{normalized_username}/{normalized_short_name}"
        f"?startapp=invite_{quote_plus(token)}"
    )


def build_miniapp_event_url(
    *, miniapp_base_url: str | None, public_token: str | None
) -> str | None:
    if not miniapp_base_url or not public_token:
        return None

    return f"{miniapp_base_url.rstrip('/')}/events/{quote_plus(public_token)}"


def build_public_miniapp_event_url(
    *, miniapp_base_url: str | None, public_token: str | None
) -> str | None:
    if not is_public_https_url(miniapp_base_url):
        return None
    return build_miniapp_event_url(
        miniapp_base_url=miniapp_base_url,
        public_token=public_token,
    )


def is_public_https_url(url: str | None) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()
    return hostname not in {"localhost", "127.0.0.1", "0.0.0.0"}


def build_telegram_share_link(*, url: str, text: str | None = None) -> str:
    if not url:
        return f"https://t.me/share/url?text={quote_plus(text)}" if text else "https://t.me/share/url"
    share_url = f"https://t.me/share/url?url={quote_plus(url)}"
    if text:
        share_url += f"&text={quote_plus(text)}"
    return share_url


def build_telegram_text_share_link(*, text: str, url: str | None = None) -> str:
    message = f"{text}\n\n{url}" if url else text
    return build_telegram_share_link(url="", text=message)


def normalize_username(username: str | None) -> str | None:
    if not username:
        return None

    clean = username.strip()
    if clean.startswith("@"):
        clean = clean[1:]

    return clean or None
