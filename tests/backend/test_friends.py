import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.friends import (
    avatar_payload,
    canonical_pair,
    display_name,
    invite_token_hash,
    telegram_url,
)
from app.web.routers.friends import _validate_invite_token


def test_canonical_pair_orders_ids_and_rejects_self():
    assert canonical_pair(20, 10) == (10, 20)
    assert canonical_pair(10, 20) == (10, 20)

    with pytest.raises(HTTPException) as exc:
        canonical_pair(10, 10)

    assert exc.value.status_code == 400


def test_invite_token_hash_does_not_store_raw_token():
    token = "a" * 32

    hashed = invite_token_hash(token)

    assert hashed != token
    assert hashed == invite_token_hash(token)
    assert len(hashed) == 64


def test_validate_invite_token_accepts_only_bounded_safe_tokens():
    token = "Ab_09-" * 6

    assert _validate_invite_token(token) == token
    assert _validate_invite_token(f"  {token}  ") == token

    for value in (None, "", "short", "x" * 257, "../" + "a" * 32):
        with pytest.raises(HTTPException) as exc:
            _validate_invite_token(value)
        assert exc.value.status_code == 404


def test_display_name_prefers_nickname_then_email_then_telegram_identity():
    assert display_name(User(nickname="john.doe")) == "John Doe"
    assert display_name(User(email="jane.smith@nu.edu.kz")) == "Jane Smith"
    assert display_name(User(username="student_user")) == "Student_user"
    assert display_name(User()) == "Nu student"


def test_avatar_payload_uses_photo_then_safe_avatar_url_then_initials():
    with_photo = User(
        id=1,
        nickname="john.doe",
        telegram_id=100,
        photo_url="https://example.com/photo.jpg",
    )
    assert avatar_payload(with_photo) == {
        "url": "https://example.com/photo.jpg",
        "initials": "JD",
    }

    with_telegram_id = User(id=2, nickname="single", telegram_id=200)
    assert avatar_payload(with_telegram_id) == {
        "url": "/api/events/avatar/200?v=200",
        "initials": "S",
    }

    anonymous = User(id=3, telegram_id=-1)
    assert avatar_payload(anonymous) == {"url": None, "initials": "NS"}


def test_telegram_url_exposes_only_known_telegram_identity():
    assert (
        telegram_url(User(username="nu_user", telegram_id=10)) == "https://t.me/nu_user"
    )
    assert telegram_url(User(telegram_id=10)) == "tg://user?id=10"
    assert telegram_url(User(telegram_id=-10)) is None
