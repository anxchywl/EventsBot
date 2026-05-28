from app.web.routers.events import router as events_router
from app.web.routers.favorites import router as favorites_router
from app.web.routers.media import router as media_router
from app.web.routers.reminders import router as reminders_router
from app.web.routers.sharing import router as sharing_router
from app.web.routers.auth import router as auth_router
from app.web.routers.ratings import router as ratings_router

__all__ = (
    "events_router",
    "favorites_router",
    "media_router",
    "reminders_router",
    "sharing_router",
    "auth_router",
    "ratings_router",
)
