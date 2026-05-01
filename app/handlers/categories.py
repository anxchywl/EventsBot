import logging
from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chat import ChatCategorySetting
from app.models.event import EventCategory
from app.services.chats import (
    get_chat_by_telegram_id,
    register_chat,
)
from app.services.users import upsert_user_from_telegram

# defines the categories router
router = Router(name="categories")
logger = logging.getLogger(__name__)


# tracks editing state for categories
class CategoryStates(StatesGroup):
    editing = State()


# verifies admin permissions for chat management
async def check_admin_permission(event: Message | CallbackQuery, bot: Bot) -> bool:
    user_id = event.from_user.id
    settings = get_settings()

    # check global bot admins
    if user_id in settings.admin_ids:
        return True

    # check group chat administrators
    chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
    if chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        try:
            member = await bot.get_chat_member(chat.id, user_id)
            if member.status in {
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
                "owner",  # some versions/clients use owner
            }:
                return True
        except Exception as e:
            logger.warning(f"failed to check admin status for {user_id}: {e}")

    return False


# builds the inline keyboard for category selection
def get_category_settings_keyboard(categories: list, enabled_ids: set):
    builder = InlineKeyboardBuilder()
    for cat in categories:
        status_emoji = "✅" if cat.id in enabled_ids else "❌"
        builder.button(
            text=f"{status_emoji} {cat.name}",
            callback_data=f"toggle_cat_{cat.id}",
        )
    builder.adjust(1)
    builder.button(text="✅ Done", callback_data="categories_done")
    return builder.as_markup()


# enters category management via command
@router.message(Command("categories"))
async def cmd_categories(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    # restrict access to admins
    if not await check_admin_permission(message, bot):
        return

    # ensure user and chat are registered
    user = await upsert_user_from_telegram(session, message.from_user)
    chat = await register_chat(session, message.chat, user.id)
    await session.commit()

    # load active categories from database
    cat_result = await session.execute(
        select(EventCategory)
        .where(EventCategory.is_active.is_(True))
        .order_by(EventCategory.sort_order, EventCategory.name)
    )
    categories = list(cat_result.scalars().all())

    # load currently enabled categories
    set_result = await session.execute(
        select(ChatCategorySetting.category_id).where(
            ChatCategorySetting.chat_id == chat.id,
            ChatCategorySetting.is_enabled.is_(True),
        )
    )
    enabled_ids = set(set_result.scalars().all())

    # store selection state and original command message in fsm
    await state.set_state(CategoryStates.editing)
    await state.update_data(
        chat_id=chat.id,
        all_categories=[{"id": c.id, "name": c.name} for c in categories],
        enabled_ids=list(enabled_ids),
        command_message_id=message.message_id,
    )

    # prompt for category selection
    await message.answer(
        "🏷 **Manage Categories**\n\n"
        "Select which event categories you want to see in this chat. "
        "Changes will be applied once you click **Done**.",
        reply_markup=get_category_settings_keyboard(categories, enabled_ids),
        parse_mode="Markdown",
    )


# finalizes and saves category changes
@router.callback_query(F.data == "categories_done", CategoryStates.editing)
async def process_categories_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
):
    # verify permission again before saving
    if not await check_admin_permission(callback, bot):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    # retrieve pending changes from fsm
    data = await state.get_data()
    chat_id = data.get("chat_id")
    enabled_ids = set(data.get("enabled_ids", []))
    all_categories = data.get("all_categories", [])

    # update database records
    if chat_id:
        for cat_info in all_categories:
            cat_id = cat_info["id"]
            is_enabled = cat_id in enabled_ids

            result = await session.execute(
                select(ChatCategorySetting).where(
                    ChatCategorySetting.chat_id == chat_id,
                    ChatCategorySetting.category_id == cat_id,
                )
            )
            setting = result.scalar_one_or_none()
            if setting:
                setting.is_enabled = is_enabled
            else:
                session.add(
                    ChatCategorySetting(
                        chat_id=chat_id, category_id=cat_id, is_enabled=is_enabled
                    )
                )

        await session.commit()

        # signal dashboard bus to refresh this chat
        try:
            from app.services.dashboard_bus import get_bus

            get_bus().schedule_refresh({chat_id})
        except Exception:
            pass

    # cleanup both the bot message and the original command
    command_message_id = data.get("command_message_id")
    try:
        await callback.message.delete()
    except Exception:
        pass

    if command_message_id:
        try:
            # bots can only delete user messages in groups/channels if they are admin
            if callback.message.chat.type != ChatType.PRIVATE:
                await bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=command_message_id,
                )
        except Exception as e:
            logger.warning(f"failed to delete command message: {e}")

    # cleanup the registration message from /register_chat if it exists
    if chat_id:
        try:
            from app.models.chat import Chat

            chat = await session.get(Chat, chat_id)
            if chat and chat.registration_message_id:
                await bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=chat.registration_message_id,
                )
                chat.registration_message_id = None
                await session.commit()
        except Exception as e:
            logger.warning(f"failed to delete registration message: {e}")

    await state.clear()
    await callback.answer("Settings saved.")


# toggles category selection in state
@router.callback_query(F.data.startswith("toggle_cat_"), CategoryStates.editing)
async def process_toggle_category(callback: CallbackQuery, state: FSMContext, bot: Bot):
    # verify permission before toggling
    if not await check_admin_permission(callback, bot):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    # update enabled list in fsm
    category_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    enabled_ids = set(data.get("enabled_ids", []))

    if category_id in enabled_ids:
        enabled_ids.remove(category_id)
    else:
        enabled_ids.add(category_id)

    await state.update_data(enabled_ids=list(enabled_ids))

    # rebuild keyboard from state data
    from collections import namedtuple

    CatProxy = namedtuple("CatProxy", ["id", "name"])
    categories = [
        CatProxy(id=c["id"], name=c["name"]) for c in data.get("all_categories", [])
    ]

    # refresh the message keyboard
    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_category_settings_keyboard(categories, enabled_ids)
        )
    except Exception:
        pass

    await callback.answer()
