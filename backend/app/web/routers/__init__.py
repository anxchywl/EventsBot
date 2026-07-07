from app.web.routers.events import router as events_router
from app.web.routers.favorites import router as favorites_router
from app.web.routers.friends import router as friends_router
from app.web.routers.media import router as media_router
from app.web.routers.reminders import router as reminders_router
from app.web.routers.sharing import router as sharing_router
from app.web.routers.auth import router as auth_router
from app.web.routers.ratings import router as ratings_router
from app.web.routers.admin import router as admin_router
from app.web.routers.flutter_auth import router as flutter_auth_router
from app.web.routers.flutter_events import router as flutter_events_router
from app.web.routers.flutter_analytics import router as flutter_analytics_router

__all__ = (
    "events_router",
    "favorites_router",
    "friends_router",
    "media_router",
    "reminders_router",
    "sharing_router",
    "auth_router",
    "ratings_router",
    "admin_router",
    "flutter_auth_router",
    "flutter_events_router",
    "flutter_analytics_router",
)
