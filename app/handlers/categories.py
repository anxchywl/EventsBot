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
    builder.button(text="Done", callback_data="categories_done")
    return builder.as_markup()


async def load_category_selection(
    session: AsyncSession,
    chat_id: int,
) -> tuple[list[EventCategory], set[int]]:
    cat_result = await session.execute(
        select(EventCategory)
        .where(EventCategory.is_active.is_(True))
        .order_by(EventCategory.sort_order, EventCategory.name)
    )
    categories = list(cat_result.scalars().all())

    set_result = await session.execute(
        select(ChatCategorySetting.category_id).where(
            ChatCategorySetting.chat_id == chat_id,
            ChatCategorySetting.is_enabled.is_(True),
        )
    )
    enabled_ids = set(set_result.scalars().all())
    return categories, enabled_ids


async def show_category_chooser_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    categories: list[EventCategory],
    enabled_ids: set[int],
) -> None:
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text="Select which event categories you want to see in this chat.",
        reply_markup=get_category_settings_keyboard(categories, enabled_ids),
    )


def enabled_ids_from_markup(callback: CallbackQuery) -> set[int]:
    enabled_ids: set[int] = set()
    if not callback.message or not callback.message.reply_markup:
        return enabled_ids

    for row in callback.message.reply_markup.inline_keyboard:
        for button in row:
            data = button.callback_data or ""
            if not data.startswith("toggle_cat_"):
                continue
            try:
                category_id = int(data.split("_")[2])
            except (IndexError, ValueError):
                continue
            if button.text.startswith("✅"):
                enabled_ids.add(category_id)
    return enabled_ids


async def save_category_selection(
    session: AsyncSession,
    chat_id: int,
    enabled_ids: set[int],
    categories: list[EventCategory],
) -> None:
    for category in categories:
        is_enabled = category.id in enabled_ids
        result = await session.execute(
            select(ChatCategorySetting).where(
                ChatCategorySetting.chat_id == chat_id,
                ChatCategorySetting.category_id == category.id,
            )
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.is_enabled = is_enabled
        else:
            session.add(
                ChatCategorySetting(
                    chat_id=chat_id,
                    category_id=category.id,
                    is_enabled=is_enabled,
                )
            )


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
    chat = await register_chat(session, message.chat, user.id, bot_id=bot.id)
    await session.commit()

    categories, enabled_ids = await load_category_selection(session, chat.id)

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
        "Select which event categories you want to see in this chat.",
        reply_markup=get_category_settings_keyboard(categories, enabled_ids),
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
        from collections import namedtuple

        CatProxy = namedtuple("CatProxy", ["id", "name"])
        categories = [
            CatProxy(id=c["id"], name=c["name"]) for c in all_categories
        ]
        await save_category_selection(session, chat_id, enabled_ids, categories)

        await session.commit()

        # cleanup the setup message if it exists, mark categories selected, and auto-create dashboard
    if chat_id:
        try:
            from app.models.chat import Chat
            from app.services.dashboard import create_or_update_dashboard_message

            chat = await session.get(Chat, chat_id)
            if chat:
                chat.categories_selected = True
                
                if chat.setup_message_id:
                    try:
                        await bot.delete_message(
                            chat_id=callback.message.chat.id,
                            message_id=chat.setup_message_id,
                        )
                    except Exception as e:
                        logger.warning(f"failed to delete setup message: {e}")
                    chat.setup_message_id = None
                
                await session.commit()

                # Automatically create or update the dashboard immediately
                await create_or_update_dashboard_message(session=session, bot=bot, chat=chat)
                await session.commit()

            # signal dashboard bus to refresh this chat just in case
            try:
                from app.services.dashboard_bus import get_bus
                get_bus().schedule_refresh({chat_id})
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"failed during post-categories setup: {e}")

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


@router.callback_query(F.data == "categories_done")
async def process_categories_done_without_state(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    if not await check_admin_permission(callback, bot):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    chat = await get_chat_by_telegram_id(session, callback.message.chat.id)
    if not chat:
        await callback.answer("Chat is not registered.", show_alert=True)
        return

    categories, _ = await load_category_selection(session, chat.id)
    enabled_ids = enabled_ids_from_markup(callback)
    await save_category_selection(session, chat.id, enabled_ids, categories)
    chat.categories_selected = True
    chat.setup_message_id = None

    from app.models.chat import DashboardMessage

    dashboard_message = await session.scalar(
        select(DashboardMessage).where(DashboardMessage.chat_id == chat.id)
    )
    if dashboard_message:
        dashboard_message.message_id = callback.message.message_id
    else:
        session.add(
            DashboardMessage(
                chat_id=chat.id,
                message_id=callback.message.message_id,
            )
        )
    await session.commit()

    from app.services.dashboard import create_or_update_dashboard_message

    await create_or_update_dashboard_message(session=session, bot=bot, chat=chat)
    await session.commit()
    await callback.answer("Settings saved.")


@router.callback_query(F.data.startswith("toggle_cat_"))
async def process_toggle_category_without_state(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    if not await check_admin_permission(callback, bot):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    chat = await get_chat_by_telegram_id(session, callback.message.chat.id)
    if not chat:
        await callback.answer("Chat is not registered.", show_alert=True)
        return

    categories, _ = await load_category_selection(session, chat.id)
    category_id = int(callback.data.split("_")[2])
    enabled_ids = enabled_ids_from_markup(callback)
    if category_id in enabled_ids:
        enabled_ids.remove(category_id)
    else:
        enabled_ids.add(category_id)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_category_settings_keyboard(categories, enabled_ids)
        )
    except Exception:
        pass

    await callback.answer()
