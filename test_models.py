import traceback
from sqlalchemy import select
from sqlalchemy.orm import configure_mappers
from app.models.user import User
from app.models.code import EmailVerificationCode
from app.models.password_reset import PasswordResetCode
from app.models.favorite import Favorite
from app.models.reminder import Reminder
from app.models.rating import Rating
from app.models.comment import Comment
from app.models.event import Event
from app.models.club import Club
from app.models.analytics import EventAnalytics
from app.models.moderation import ModerationLog
from app.models.chat import Chat

try:
    configure_mappers()
    print("Mappers configured successfully!")
    stmt = select(User)
    print("Statement compiled successfully!")
except Exception as e:
    traceback.print_exc()
