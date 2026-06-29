import pytest
from unittest.mock import AsyncMock, patch

from app.models.user import User
from app.models.event import Event
from app.config import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        admin_ids=[111],
        moderator_chat_id=-222,
        bot_token="test:test",
        app_timezone="UTC",
        web_base_url="http://test",
        jwt_secret="test",
        bot_webhook_url="http://test",
        miniapp_url="http://test",
    )


@pytest.mark.anyio
async def test_telegram_edit_event_ownership(mock_settings):
    from app.handlers.event_edit import start_edit_event
    from aiogram.types import CallbackQuery, User as TgUser

    event = Event(id=10, creator_user_id=1, status="approved")

    cb = AsyncMock(spec=CallbackQuery)
    cb.from_user = TgUser(id=2, is_bot=False, first_name="test")
    cb.data = "edit_event_10"
    cb.message = AsyncMock()

    session = AsyncMock()
    state = AsyncMock()

    with (
        patch("app.handlers.event_edit.get_settings", return_value=mock_settings),
        patch("app.handlers.event_edit.get_event_by_id", return_value=event),
    ):
        cb.answer = AsyncMock()
        await start_edit_event(cb, state, session)

        cb.answer.assert_called_with("Unauthorized.", show_alert=True)


@pytest.mark.anyio
async def test_telegram_delete_event_ownership(mock_settings):
    from app.handlers.user_events import process_delete_event
    from aiogram.types import CallbackQuery, User as TgUser

    event = Event(id=10, creator_user_id=1, status="approved")

    cb = AsyncMock(spec=CallbackQuery)
    cb.from_user = TgUser(id=2, is_bot=False, first_name="test")
    cb.data = "delete_event_10"

    session = AsyncMock()

    with (
        patch("app.handlers.user_events.get_settings", return_value=mock_settings),
        patch("app.handlers.user_events.get_event_by_id", return_value=event),
    ):
        cb.answer = AsyncMock()
        await process_delete_event(cb, session)

        cb.answer.assert_called_with("Unauthorized.", show_alert=True)


@pytest.mark.anyio
async def test_telegram_moderation_requires_role(mock_settings):
    from app.handlers.moderation import process_approve
    from aiogram.types import CallbackQuery, User as TgUser, Message, Chat

    cb = AsyncMock(spec=CallbackQuery)
    cb.from_user = TgUser(id=2, is_bot=False, first_name="test")
    cb.fromuser = cb.from_user
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = Chat(id=333, type="private")
    cb.data = "mod_approve_10"

    session = AsyncMock()
    bot = AsyncMock()

    with (
        patch("app.handlers.moderation.get_settings", return_value=mock_settings),
        patch(
            "app.handlers.moderation.upsert_user_from_telegram",
            return_value=User(id=2, telegram_id=2),
        ),
    ):
        cb.answer = AsyncMock()
        await process_approve(cb, session, bot)

        cb.answer.assert_called_with("Unauthorized.", show_alert=True)
