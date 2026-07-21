"""Generate and remove a namespaced synthetic analytics dataset."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import random
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.models.analytics import EventAnalytics  # noqa: E402
from app.models.comment import Comment  # noqa: E402
from app.models.event import Event, EventCategory  # noqa: E402
from app.models.enums import EventStatus, ModerationAction, ReminderStatus, ReminderType  # noqa: E402
from app.models.favorite import Favorite  # noqa: E402
from app.models.moderation import ModerationLog  # noqa: E402
from app.models.rating import Rating  # noqa: E402
from app.models.reminder import Reminder  # noqa: E402
from app.models.user import User  # noqa: E402

SOURCE_URL = "https://nu.edu.kz/inf-media/events-page/?mode=timeline"
FICTIONAL_FIRST_NAMES = (
    "Amina",
    "Timur",
    "Dana",
    "Arman",
    "Mira",
    "Dias",
    "Alina",
    "Nursultan",
    "Madina",
    "Ilya",
    "Aruzhan",
    "Bekzat",
    "Kamila",
    "Marat",
    "Saniya",
    "Ruslan",
    "Aigerim",
    "Eldar",
    "Zarina",
    "Maksim",
    "Laura",
    "Adil",
    "Sofia",
    "Rinat",
    "Aisulu",
)
FICTIONAL_LAST_NAMES = (
    "Sadykova",
    "Kassenov",
    "Muratbek",
    "Nurlanov",
    "Beketova",
    "Akhmetov",
    "Yessenova",
    "Karimov",
    "Ospanova",
    "Volkov",
    "Tulegenova",
    "Iskakov",
    "Baimukhan",
    "Serikova",
    "Kadyrov",
    "Mukhanova",
    "Abdullin",
    "Zhaksybek",
    "Orlova",
    "Saparov",
    "Kenzhebaeva",
    "Aubakirov",
    "Nazarova",
    "Khalilov",
    "Temirova",
)
REVIEW_TEXTS = (
    "Clear programme and a well-organized session.",
    "The speakers were engaging and the discussion was useful.",
    "A good event with practical takeaways.",
    "Helpful format, friendly atmosphere, and good timing.",
    "I enjoyed the conversation and would attend again.",
)
SOURCE_URLS = (
    "https://nu.edu.kz/inf-media/events-page/?action=nu_events_filter&mode=upcoming",
    "https://nu.edu.kz/inf-media/events-page/?action=nu_events_filter&mode=trending",
    "https://nu.edu.kz/inf-media/events-page/?action=nu_events_filter&mode=past",
)
TZ = ZoneInfo("Asia/Almaty")
DEFAULT_CATEGORIES = {
    "conference": "Conferences",
    "seminar": "Seminars",
    "workshop": "Workshops",
    "lecture": "Guest Lectures",
    "student_activity": "Student Activities",
    "webinar": "Webinars",
}
SYNTHETIC_ROLES = ("user", "coordinator", "admin")


@dataclass(frozen=True)
class SourceEvent:
    title: str
    event_date: date
    url: str
    image_url: str | None = None
    description: str | None = None
    organizer: str | None = None
    location: str | None = None
    registration_url: str | None = None
    start_time: time | None = None
    end_time: time | None = None


class CatalogueParser(HTMLParser):
    def __init__(self, source_url: str):
        super().__init__()
        self.source_url = source_url
        self.in_heading = False
        self.heading: list[str] = []
        self.href: str | None = None
        self.image_url: str | None = None
        self.items: list[SourceEvent] = []
        self.pending_title: str | None = None
        self.in_card_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        classes = (attrs_map.get("class") or "").split()
        if tag == "h3" or (tag == "div" and "nu-event-title" in classes):
            self.in_heading = True
            self.in_card_title = tag == "div"
            self.heading = []
        if tag == "img" and (
            "wp-post-image" in classes or self.in_heading or not self.image_url
        ):
            image_url = attrs_map.get("src") or attrs_map.get("data-src")
            if image_url:
                self.image_url = urljoin(self.source_url, image_url)
        if self.in_heading and tag == "a":
            self.href = urljoin(self.source_url, attrs_map.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_heading or not (
            tag == "h3" or (tag == "div" and self.in_card_title)
        ):
            return
        title = " ".join("".join(self.heading).split())
        if title:
            self.pending_title = title
        self.in_heading = False
        self.in_card_title = False

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading.append(data)
        for value in re.findall(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", data):
            if self.pending_title:
                self.items.append(
                    SourceEvent(
                        self.pending_title,
                        date(int(value[2]), int(value[1]), int(value[0])),
                        self.href or self.source_url,
                        self.image_url,
                    )
                )
                self.pending_title = None
                self.image_url = None
        if self.pending_title:
            try:
                parsed_date = datetime.strptime(data.strip(), "%a, %b %d, %Y").date()
            except ValueError:
                return
            self.items.append(
                SourceEvent(
                    self.pending_title,
                    parsed_date,
                    self.href or self.source_url,
                    self.image_url,
                )
            )
            self.pending_title = None
            self.image_url = None


def fetch_catalogue(source_urls: tuple[str, ...] = SOURCE_URLS) -> list[SourceEvent]:
    catalogue: list[SourceEvent] = []
    seen_urls: set[str] = set()
    for source_url in source_urls:
        request = Request(
            source_url, headers={"User-Agent": "events-bot-synthetic-generator/1.0"}
        )
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode(
                response.headers.get_content_charset() or "utf-8", "replace"
            )
        parser = CatalogueParser(source_url)
        parser.feed(payload)
        for item in parser.items:
            canonical_url = item.url.rstrip("/")
            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)
            details = _fetch_event_details(item)
            if details is not None:
                catalogue.append(details)
    unique: list[SourceEvent] = []
    seen_titles: set[str] = set()
    seen_images: set[str] = set()
    for event in catalogue:
        title_key = event.title.casefold()
        if title_key in seen_titles or (
            event.image_url and event.image_url in seen_images
        ):
            continue
        seen_titles.add(title_key)
        if event.image_url:
            seen_images.add(event.image_url)
        unique.append(event)
    return unique


def _fetch_event_details(event: SourceEvent) -> SourceEvent | None:
    request = Request(
        event.url, headers={"User-Agent": "events-bot-synthetic-generator/1.0"}
    )
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode(
            response.headers.get_content_charset() or "utf-8", "replace"
        )
    for raw_schema in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        payload,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        try:
            schema = json.loads(html.unescape(raw_schema))
        except json.JSONDecodeError:
            continue
        candidates = schema.get("@graph", []) if isinstance(schema, dict) else []
        if isinstance(schema, dict):
            candidates = [schema, *candidates]
        details = next(
            (
                item
                for item in candidates
                if isinstance(item, dict) and item.get("@type") == "Event"
            ),
            None,
        )
        if details:
            return _source_event_from_schema(event, details)
    return None


def _source_event_from_schema(event: SourceEvent, details: dict) -> SourceEvent:
    organizer = details.get("organizer")
    if isinstance(organizer, list):
        organizer_names = [
            item.get("name") for item in organizer if isinstance(item, dict)
        ]
        organizer_name = " | ".join(name for name in organizer_names if name)
    elif isinstance(organizer, dict):
        organizer_name = organizer.get("name")
    else:
        organizer_name = None
    location = details.get("location")
    location_name = location.get("name") if isinstance(location, dict) else None
    offers = details.get("offers")
    registration_url = offers.get("url") if isinstance(offers, dict) else None
    images = details.get("image")
    image_url = images[0] if isinstance(images, list) and images else images
    start = _schema_datetime(details.get("startDate"))
    end = _schema_datetime(details.get("endDate"))
    description = re.sub(
        r"\s+", " ", html.unescape(str(details.get("description") or ""))
    ).strip()
    description = re.sub(r"<[^>]+>", "", description)
    return SourceEvent(
        title=re.sub(
            r"\s+", " ", html.unescape(str(details.get("name") or event.title))
        ).strip(),
        event_date=start.date() if start else event.event_date,
        url=str(details.get("url") or event.url),
        image_url=str(image_url) if image_url else event.image_url,
        description=description or None,
        organizer=organizer_name,
        location=location_name,
        registration_url=registration_url or str(details.get("url") or event.url),
        start_time=start.time().replace(tzinfo=None) if start else None,
        end_time=end.time().replace(tzinfo=None) if end else None,
    )


def _schema_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify(title: str) -> str:
    lowered = title.lower()
    if "conference" in lowered or "international" in lowered:
        return "conference"
    if "workshop" in lowered:
        return "workshop"
    if "webinar" in lowered:
        return "webinar"
    if "lecture" in lowered or "talk" in lowered:
        return "lecture"
    if "seminar" in lowered:
        return "seminar"
    return "student_activity"


def dataset_key(seed: int) -> str:
    return hashlib.sha256(f"events-bot-synthetic-v1:{seed}".encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Counts:
    users: int = 500
    events: int = 100
    interactions: int = 10000
    favorites: int = 1000
    reminders: int = 1000
    reviews: int = 500


def planned_counts(counts: Counts) -> dict[str, int]:
    return {
        "users": counts.users,
        "events": counts.events,
        "event_analytics": counts.interactions,
        "favorites": counts.favorites,
        "reminders": counts.reminders,
        "ratings": counts.reviews,
        "comments": counts.reviews,
    }


def synthetic_email(key: str, index: int) -> str:
    return f"synthetic-{key}-user{index:06d}@example.test"


def event_request_id(key: str, index: int) -> str:
    return f"synthetic-{key}-{index:06d}"


async def _category_map(session: AsyncSession, key: str) -> dict[str, EventCategory]:
    result = await session.execute(select(EventCategory))
    existing = {category.name.lower(): category for category in result.scalars()}
    categories: dict[str, EventCategory] = {}
    for slug, name in DEFAULT_CATEGORIES.items():
        category = existing.get(name.lower())
        if category is None:
            category = EventCategory(
                name=name, slug=f"synthetic_{key}_{slug}", sort_order=900
            )
            session.add(category)
            await session.flush()
        categories[slug] = category
    return categories


def _event_status(index: int, now: datetime) -> str:
    if index % 17 == 0:
        return EventStatus.CANCELLED.value
    if index % 19 == 0:
        return EventStatus.REJECTED.value
    if index % 23 == 0:
        return EventStatus.ARCHIVED.value
    return EventStatus.APPROVED.value if index % 7 else EventStatus.PENDING.value


def _event_date(
    index: int, catalogue: list[SourceEvent], rng: random.Random, today: date
) -> date:
    if catalogue:
        source = catalogue[index % len(catalogue)]
        if source.event_date < today:
            return today + timedelta(days=7 + index * 3)
        return source.event_date
    return today + timedelta(days=index * 3 - 150)


async def generate(
    session: AsyncSession, *, seed: int, counts: Counts, catalogue: list[SourceEvent]
) -> dict[str, int]:
    key = dataset_key(seed)
    rng = random.Random(seed)
    now = datetime.now(TZ).replace(microsecond=0)
    categories = await _category_map(session, key)
    existing_users = (
        (
            await session.execute(
                select(User).where(User.email.like(f"synthetic-{key}-%@example.test"))
            )
        )
        .scalars()
        .all()
    )
    users = {user.email: user for user in existing_users}
    for index in range(1, counts.users + 1):
        email = synthetic_email(key, index)
        if email not in users:
            name_index = (index - 1) % (
                len(FICTIONAL_FIRST_NAMES) * len(FICTIONAL_LAST_NAMES)
            )
            first_name = FICTIONAL_FIRST_NAMES[name_index % len(FICTIONAL_FIRST_NAMES)]
            last_name = FICTIONAL_LAST_NAMES[name_index // len(FICTIONAL_FIRST_NAMES)]
            user = User(
                telegram_id=9_000_000_000 + seed * 100_000 + index,
                username=f"synthetic_user_{key}_{index:06d}",
                first_name=first_name,
                last_name=last_name,
                email=email,
                nickname=f"{first_name} {last_name}",
                photo_url=f"https://api.dicebear.com/9.x/personas/svg?seed={key}-{index}",
                is_verified=True,
                role="admin"
                if index <= 3
                else "coordinator"
                if index <= 23
                else "user",
                last_active_at=now - timedelta(days=rng.randint(0, 180)),
            )
            session.add(user)
            users[email] = user
    await session.flush()
    user_list = list(users.values())[: counts.users]
    existing_events = (
        (
            await session.execute(
                select(Event).where(Event.client_request_id.like(f"synthetic-{key}-%"))
            )
        )
        .scalars()
        .all()
    )
    if existing_events:
        return {**planned_counts(counts), "dataset_key": key, "already_present": 1}
    events = {event.client_request_id: event for event in existing_events}
    event_count = min(counts.events, len(catalogue))
    for index in range(event_count):
        request_id = event_request_id(key, index)
        if request_id in events:
            continue
        source = (
            catalogue[index % len(catalogue)]
            if catalogue
            else SourceEvent(
                f"Campus Event {index + 1}",
                _event_date(index, [], rng, now.date()),
                SOURCE_URL,
            )
        )
        category_slug = classify(source.title)
        start = source.start_time or time(
            rng.choice(range(9, 19)), rng.choice((0, 15, 30, 45))
        )
        end = (
            source.end_time
            or (
                datetime.combine(now.date(), start)
                + timedelta(hours=rng.choice((1, 2, 3)))
            ).time()
        )
        creator = user_list[index % max(1, min(20, len(user_list)))]
        event = Event(
            client_request_id=request_id,
            client_request_fingerprint=hashlib.sha256(request_id.encode()).hexdigest(),
            creator_user_id=creator.id,
            category_id=categories[category_slug].id,
            title=source.title[:100],
            description=(source.description or source.title)[:1000],
            event_date=_event_date(index, catalogue, rng, now.date()),
            event_time=start,
            event_end_time=end,
            timezone="Asia/Almaty",
            location=(source.location or "Nazarbayev University")[:100],
            organizer_name=(source.organizer or "Nazarbayev University")[:100],
            registration_url=source.registration_url or source.url,
            poster_file_id=source.image_url,
            status=_event_status(index, now),
        )
        if event.status == EventStatus.APPROVED.value:
            event.approved_by_user_id = user_list[0].id
            event.approved_at = now - timedelta(days=rng.randint(1, 120))
        if event.status == EventStatus.CANCELLED.value:
            event.cancelled_at = now - timedelta(days=1)
        session.add(event)
        events[request_id] = event
    await session.flush()
    event_list = list(events.values())[:event_count]
    for event in event_list:
        session.add(
            ModerationLog(
                event_id=event.id,
                actor_user_id=event.creator_user_id,
                action=ModerationAction.SUBMITTED.value,
                created_at=now - timedelta(days=130),
            )
        )
        if event.status in {
            EventStatus.APPROVED.value,
            EventStatus.ARCHIVED.value,
            EventStatus.CANCELLED.value,
        }:
            session.add(
                ModerationLog(
                    event_id=event.id,
                    actor_user_id=user_list[0].id,
                    action=ModerationAction.APPROVED.value,
                    created_at=now - timedelta(days=120),
                )
            )
        if event.status in {EventStatus.REJECTED.value, EventStatus.CANCELLED.value}:
            session.add(
                ModerationLog(
                    event_id=event.id,
                    actor_user_id=user_list[0].id,
                    action=event.status,
                    created_at=now - timedelta(days=1),
                )
            )
    approved = [
        event for event in event_list if event.status == EventStatus.APPROVED.value
    ]
    pairs: set[tuple[int, int]] = set()
    for index in range(counts.interactions):
        if not approved:
            break
        event = approved[int((rng.random() ** 2) * len(approved))]
        user = user_list[rng.randrange(len(user_list))]
        action = rng.choices(
            (
                "open",
                "open_from_share",
                "register_click",
                "share_click",
                "favorite_add",
                "reminder_create",
            ),
            weights=(50, 8, 10, 8, 16, 8),
        )[0]
        session.add(
            EventAnalytics(
                event_id=event.id,
                user_id=user.id,
                action=action,
                source=rng.choice(("search", "feed", "share", "category")),
                created_at=now
                - timedelta(days=rng.randint(0, 180), hours=rng.randint(0, 23)),
            )
        )
    while len(pairs) < min(counts.favorites, len(user_list) * len(approved)):
        if not approved:
            break
        user = user_list[rng.randrange(len(user_list))]
        event = approved[rng.randrange(len(approved))]
        if (user.id, event.id) not in pairs:
            pairs.add((user.id, event.id))
            session.add(
                Favorite(
                    user_id=user.id,
                    event_id=event.id,
                    created_at=now - timedelta(days=rng.randint(0, 90)),
                )
            )
    upcoming = [event for event in approved if event.event_date >= now.date()]
    reminder_pairs: set[tuple[int, int, int]] = set()
    while len(reminder_pairs) < min(
        counts.reminders, len(user_list) * len(upcoming) * 2
    ):
        if not upcoming:
            break
        user = user_list[rng.randrange(len(user_list))]
        event = upcoming[rng.randrange(len(upcoming))]
        offset = rng.choice((60, 1440))
        pair = (user.id, event.id, offset)
        if pair in reminder_pairs:
            continue
        reminder_pairs.add(pair)
        event_start = datetime.combine(event.event_date, event.event_time, TZ)
        session.add(
            Reminder(
                user_id=user.id,
                event_id=event.id,
                remind_at=event_start - timedelta(minutes=offset),
                offset_minutes=offset,
                reminder_type=ReminderType.ONE_HOUR.value
                if offset == 60
                else ReminderType.ONE_DAY.value,
                status=ReminderStatus.SCHEDULED.value,
            )
        )
    review_pairs: set[tuple[int, int]] = set()
    while len(review_pairs) < min(counts.reviews, len(user_list) * len(approved)):
        if not approved:
            break
        user = user_list[rng.randrange(len(user_list))]
        event = approved[rng.randrange(len(approved))]
        if (user.id, event.id) in review_pairs:
            continue
        review_pairs.add((user.id, event.id))
        reviewed_at = now - timedelta(days=rng.randint(0, 60))
        session.add(
            Rating(
                user_id=user.id,
                event_id=event.id,
                score=rng.choices((3, 4, 5), weights=(1, 3, 6))[0],
                created_at=reviewed_at,
                updated_at=reviewed_at,
            )
        )
        session.add(
            Comment(
                user_id=user.id,
                event_id=event.id,
                content=rng.choice(REVIEW_TEXTS),
                created_at=reviewed_at,
                updated_at=reviewed_at,
            )
        )
    await session.commit()
    return {
        **planned_counts(counts),
        "events": len(event_list),
        "dataset_key": key,
    }


async def cleanup(session: AsyncSession, key: str) -> dict[str, int]:
    users = (
        (
            await session.execute(
                select(User.id).where(
                    User.email.like(f"synthetic-{key}-%@example.test")
                )
            )
        )
        .scalars()
        .all()
    )
    events = (
        (
            await session.execute(
                select(Event.id).where(
                    Event.client_request_id.like(f"synthetic-{key}-%")
                )
            )
        )
        .scalars()
        .all()
    )
    if not users and not events:
        return {"users": 0, "events": 0}
    for model, column, ids in (
        (EventAnalytics, EventAnalytics.user_id, users),
        (Favorite, Favorite.user_id, users),
        (Reminder, Reminder.user_id, users),
        (Rating, Rating.user_id, users),
        (Comment, Comment.user_id, users),
        (ModerationLog, ModerationLog.actor_user_id, users),
    ):
        if ids:
            await session.execute(delete(model).where(column.in_(ids)))
    if events:
        for model in (
            EventAnalytics,
            Favorite,
            Reminder,
            Rating,
            Comment,
            ModerationLog,
        ):
            await session.execute(delete(model).where(model.event_id.in_(events)))
        await session.execute(delete(Event).where(Event.id.in_(events)))
    if users:
        await session.execute(delete(User).where(User.id.in_(users)))
    await session.execute(
        delete(EventCategory).where(EventCategory.slug.like(f"synthetic_{key}_%"))
    )
    await session.commit()
    return {"users": len(users), "events": len(events)}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--events", type=int, default=100)
    parser.add_argument("--interactions", type=int, default=10000)
    parser.add_argument("--favorites", type=int, default=1000)
    parser.add_argument("--reminders", type=int, default=1000)
    parser.add_argument("--reviews", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cleanup-key")
    parser.add_argument("--allow-production", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = _args()
    database_url = args.database_url.lower()
    production_url = any(
        value in database_url for value in ("209.38.195.152", "production", "prod")
    )
    if production_url and not args.allow_production:
        raise SystemExit(
            "refusing production-like database; use --allow-production only after explicit approval"
        )
    if args.cleanup_key and not re.fullmatch(r"[0-9a-f]{12}", args.cleanup_key):
        raise SystemExit("cleanup key must be a 12-character hexadecimal dataset key")
    engine = create_async_engine(args.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        if args.cleanup_key:
            print(await cleanup(session, args.cleanup_key))
        else:
            counts = Counts(
                args.users,
                args.events,
                args.interactions,
                args.favorites,
                args.reminders,
                args.reviews,
            )
            if args.dry_run:
                print(
                    {
                        **planned_counts(counts),
                        "dataset_key": dataset_key(args.seed),
                        "dry_run": True,
                    }
                )
            else:
                print(
                    await generate(
                        session,
                        seed=args.seed,
                        counts=counts,
                        catalogue=fetch_catalogue(),
                    )
                )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
