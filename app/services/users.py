from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models.user import User


# creates or refreshes a user from telegram data
async def upsert_user_from_telegram(
    session: AsyncSession,
    telegram_user: TelegramUser,
) -> User:
    # look up the user by telegram id
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_user.id),
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(telegram_id=telegram_user.id)
        session.add(user)

    from app.config import get_settings
    settings = get_settings()
    if telegram_user.id in settings.admin_ids:
        user.role = "admin"

    # keep profile fields in sync with telegram
    user.username = telegram_user.username
    user.first_name = telegram_user.first_name
    user.last_name = telegram_user.last_name
    user.language_code = telegram_user.language_code
    user.is_bot = telegram_user.is_bot
    user.last_active_at = datetime.now()

    await session.flush()
    return user
