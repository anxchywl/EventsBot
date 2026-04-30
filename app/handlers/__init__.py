from app.handlers.admin_chat import router as admin_chat_router
from app.handlers.admin_panel import router as admin_panel_router
from app.handlers.event_edit import router as event_edit_router
from app.handlers.event_submission import router as event_submission_router
from app.handlers.events import router as events_router
from app.handlers.moderation import router as moderation_router
from app.handlers.start import router as start_router
from app.handlers.user_events import router as user_events_router

__all__ = (
    "admin_chat_router",
    "admin_panel_router",
    "start_router",
    "event_submission_router",
    "moderation_router",
    "events_router",
    "user_events_router",
    "event_edit_router",
)
