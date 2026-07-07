"""Backend-computed analytics for the coordinator dashboard.

Every number the Flutter Event Manager screen renders is produced here with
grouped SQL (no per-event loops / N+1) and returned as plain dicts. The Flutter
layer only renders what it is given — it never sums, averages, groups or ranks
raw rows itself.

The moderation timing/iteration derivations that depend on the *sequence* of
moderation actions per event are factored into pure functions
(``first_decision_seconds`` / ``total_review_seconds`` / ``review_iterations``)
so they can be unit-tested without a database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import Float, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.analytics import EventAnalytics
from app.models.comment import Comment
from app.models.enums import EventStatus, ModerationAction
from app.models.event import Event, EventCategory
from app.models.favorite import Favorite
from app.models.moderation import ModerationLog
from app.models.rating import Rating
from app.models.user import User

logger = logging.getLogger(__name__)

# EventAnalytics.action values grouped by the metric they feed.
VIEW_ACTIONS = ("open", "open_from_share")
REGISTER_ACTION = "register_click"
SHARE_ACTION = "share_click"
FAVORITE_ADD_ACTION = "favorite_add"
FAVORITE_REMOVE_ACTION = "favorite_remove"
REMINDER_CREATE_ACTION = "reminder_create"

# statuses that still occupy the moderation queue (awaiting a coordinator).
QUEUE_STATUSES = (
    EventStatus.PENDING.value,
    EventStatus.RESUBMITTED.value,
    EventStatus.NEEDS_CHANGES.value,
)

# moderation actions that represent a coordinator decision on a submission.
_DECISION_ACTIONS = (
    ModerationAction.APPROVED.value,
    ModerationAction.REJECTED.value,
    ModerationAction.NEEDS_CHANGES.value,
    ModerationAction.RESTORED.value,
)
_TERMINAL_ACTIONS = (
    ModerationAction.APPROVED.value,
    ModerationAction.REJECTED.value,
    ModerationAction.RESTORED.value,
)


def _app_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Filters ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnalyticsFilters:
    """Composable (AND-ed) filter set shared by every dashboard metric.

    ``date_from`` / ``date_to`` bound ``Event.created_at`` (inclusive of the whole
    end day, evaluated in the app timezone). All fields are optional; an empty
    filter set means "all events".
    """

    date_from: date | None = None
    date_to: date | None = None
    category_id: int | None = None
    organizer: str | None = None
    status: str | None = None
    event_id: int | None = None

    def event_conditions(self) -> list:
        """Return SQLAlchemy conditions to apply to an ``Event`` query.

        Every dimension is optional and ANDs with the others, so new filter
        dimensions can be added here without touching any metric query.
        """
        tz = _app_tz()
        conditions: list = []
        # a pinned single event is the strongest selector; it still composes
        # with the other dimensions (an event outside the date range yields an
        # empty — but never mixed — dataset).
        if self.event_id is not None:
            conditions.append(Event.id == self.event_id)
        if self.date_from is not None:
            start = datetime.combine(self.date_from, time.min, tzinfo=tz)
            conditions.append(Event.created_at >= start)
        if self.date_to is not None:
            # inclusive end-of-day: strictly before the following midnight
            end = datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=tz)
            conditions.append(Event.created_at < end)
        if self.category_id is not None:
            conditions.append(Event.category_id == self.category_id)
        if self.organizer:
            conditions.append(Event.organizer_name == self.organizer)
        if self.status:
            conditions.append(Event.status == self.status)
        return conditions


def _filtered_event_ids(filters: AnalyticsFilters):
    """Subquery selecting the ids of events matching the active filters.

    Used to constrain child-table aggregations (analytics/ratings/favorites/logs)
    to the same event set every panel sees, so no widget shows unfiltered data.
    """
    stmt = select(Event.id)
    conditions = filters.event_conditions()
    if conditions:
        stmt = stmt.where(and_(*conditions))
    return stmt.scalar_subquery()


# ── Pure moderation-sequence helpers (unit-tested) ───────────────────────────


@dataclass
class _LogEntry:
    action: str
    created_at: datetime


def _submission_start(logs: list[_LogEntry], fallback: datetime | None) -> datetime | None:
    """Timestamp the review clock starts from: the first 'submitted' log, else
    the provided fallback (the event's created_at)."""
    for entry in logs:
        if entry.action == ModerationAction.SUBMITTED.value:
            return entry.created_at
    return fallback


def first_decision_seconds(
    logs: list[_LogEntry], fallback_start: datetime | None
) -> float | None:
    """Seconds from submission to the *first* coordinator decision, or None if
    no decision has been made yet."""
    start = _submission_start(logs, fallback_start)
    if start is None:
        return None
    for entry in logs:
        if entry.action in _DECISION_ACTIONS and entry.created_at >= start:
            delta = (entry.created_at - start).total_seconds()
            return max(delta, 0.0)
    return None


def total_review_seconds(
    logs: list[_LogEntry], fallback_start: datetime | None
) -> float | None:
    """Seconds from submission to the *final* terminal decision (approved or
    rejected), including any needs_changes → resubmit back-and-forth. None if the
    event never reached a terminal decision."""
    start = _submission_start(logs, fallback_start)
    if start is None:
        return None
    final: datetime | None = None
    for entry in logs:
        if entry.action in _TERMINAL_ACTIONS:
            final = entry.created_at
    if final is None:
        return None
    return max((final - start).total_seconds(), 0.0)


def review_iterations(logs: list[_LogEntry]) -> int | None:
    """Number of coordinator review passes for one event.

    Each approved / rejected / needs_changes / restored action is one pass, so an
    event that went needs_changes → resubmitted → approved counts as **one event**
    with **2 iterations**, never double-counted across cards. None if the event has
    not been reviewed yet.
    """
    count = sum(1 for e in logs if e.action in _DECISION_ACTIONS)
    return count or None


# ── Summary ──────────────────────────────────────────────────────────────────


async def compute_summary(
    session: AsyncSession, filters: AnalyticsFilters
) -> dict[str, float | int | None]:
    """Return the keyed summary-card metrics map.

    A keyed map (not fixed positional fields) so a new card can be added later
    without changing the response shape.
    """
    tz = _app_tz()
    conditions = filters.event_conditions()
    base = and_(*conditions) if conditions else True

    # one grouped pass for the per-status counts
    status_rows = (
        await session.execute(
            select(Event.status, func.count()).where(base).group_by(Event.status)
        )
    ).all()
    by_status = {status: count for status, count in status_rows}
    total = sum(by_status.values())

    now_local = _now_utc().astimezone(tz)
    week_start_local = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start_utc = week_start_local.astimezone(timezone.utc)
    today_local = now_local.date()

    published_this_week = (
        await session.scalar(
            select(func.count())
            .select_from(Event)
            .where(base, Event.status == EventStatus.APPROVED.value)
        )
    ) or 0

    upcoming = (
        await session.scalar(
            select(func.count())
            .select_from(Event)
            .where(
                base,
                Event.status == EventStatus.APPROVED.value,
                Event.event_date >= today_local,
            )
        )
    ) or 0

    event_ids = _filtered_event_ids(filters)

    avg_rating = await session.scalar(
        select(func.avg(cast(Rating.score, Float))).where(
            Rating.event_id.in_(event_ids), Rating.deleted_at.is_(None)
        )
    )

    total_favorites = (
        await session.scalar(
            select(func.count()).select_from(Favorite).where(Favorite.event_id.in_(event_ids))
        )
    ) or 0

    action_rows = (
        await session.execute(
            select(EventAnalytics.action, func.count())
            .where(EventAnalytics.event_id.in_(event_ids))
            .group_by(EventAnalytics.action)
        )
    ).all()
    action_counts = {action: count for action, count in action_rows}
    total_views = sum(action_counts.get(a, 0) for a in VIEW_ACTIONS)
    total_registration_clicks = action_counts.get(REGISTER_ACTION, 0)

    return {
        "total_events": total,
        # everything still awaiting a coordinator decision counts as pending:
        # freshly submitted, resubmitted after edits, and sent-back needs_changes
        "pending_review": sum(by_status.get(s, 0) for s in QUEUE_STATUSES),
        "approved": by_status.get(EventStatus.APPROVED.value, 0),
        "needs_changes": by_status.get(EventStatus.NEEDS_CHANGES.value, 0),
        "resubmitted": by_status.get(EventStatus.RESUBMITTED.value, 0),
        "rejected": by_status.get(EventStatus.REJECTED.value, 0),
        "cancelled": by_status.get(EventStatus.CANCELLED.value, 0),
        "archived": by_status.get(EventStatus.ARCHIVED.value, 0),
        "published_this_week": published_this_week,
        "upcoming_events": upcoming,
        "average_event_rating": round(float(avg_rating), 2) if avg_rating is not None else None,
        "total_favorites": total_favorites,
        "total_registration_clicks": total_registration_clicks,
        "total_event_views": total_views,
    }


# ── Moderation ───────────────────────────────────────────────────────────────


async def compute_moderation(
    session: AsyncSession,
    filters: AnalyticsFilters,
    thresholds_hours: list[int],
) -> dict:
    """Approval/rejection/needs-changes rates, review timings/iterations, queue
    health, longest-pending event, and per-threshold waiting-too-long counts."""
    conditions = filters.event_conditions()
    base = and_(*conditions) if conditions else True

    status_rows = (
        await session.execute(
            select(Event.status, func.count()).where(base).group_by(Event.status)
        )
    ).all()
    by_status = {status: count for status, count in status_rows}

    approved = by_status.get(EventStatus.APPROVED.value, 0)
    rejected = by_status.get(EventStatus.REJECTED.value, 0)
    needs_changes = by_status.get(EventStatus.NEEDS_CHANGES.value, 0)
    # rate denominator: events that have received (or are receiving) a decision.
    decided_total = sum(by_status.values())

    def _rate(n: int) -> float:
        return round(n / decided_total, 4) if decided_total else 0.0

    # pull every moderation log for the filtered events in ONE ordered query and
    # group per event in Python — no per-event round trips.
    log_rows = (
        await session.execute(
            select(
                ModerationLog.event_id,
                ModerationLog.action,
                ModerationLog.created_at,
            )
            .where(ModerationLog.event_id.in_(_filtered_event_ids(filters)))
            .order_by(ModerationLog.event_id, ModerationLog.created_at, ModerationLog.id)
        )
    ).all()

    # created_at fallback (submission start) per event, for events whose history
    # predates the moderation-log 'submitted' entry.
    created_rows = (
        await session.execute(select(Event.id, Event.created_at).where(base))
    ).all()
    created_at_by_event = {eid: created for eid, created in created_rows}

    per_event: dict[int, list[_LogEntry]] = {}
    for event_id, action, created in log_rows:
        per_event.setdefault(event_id, []).append(_LogEntry(action=action, created_at=created))

    first_decisions: list[float] = []
    total_reviews: list[float] = []
    iterations: list[int] = []
    for event_id, entries in per_event.items():
        fallback = created_at_by_event.get(event_id)
        fd = first_decision_seconds(entries, fallback)
        if fd is not None:
            first_decisions.append(fd)
        tr = total_review_seconds(entries, fallback)
        if tr is not None:
            total_reviews.append(tr)
        it = review_iterations(entries)
        if it is not None:
            iterations.append(it)

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    # queue health
    now = _now_utc()
    queue_rows = (
        await session.execute(
            select(Event.id, Event.title, Event.created_at)
            .where(base, Event.status.in_(QUEUE_STATUSES))
            .order_by(Event.created_at.asc())
        )
    ).all()
    queue_size = len(queue_rows)
    longest_pending = None
    if queue_rows:
        eid, title, created = queue_rows[0]
        longest_pending = {
            "event_id": eid,
            "title": title,
            "waiting_seconds": max((now - created).total_seconds(), 0.0),
        }

    threshold_buckets = []
    for hours in thresholds_hours:
        cutoff = now - timedelta(hours=hours)
        count = sum(1 for _, _, created in queue_rows if created <= cutoff)
        threshold_buckets.append({"threshold_hours": hours, "count": count})

    return {
        "approval_rate": _rate(approved),
        "rejection_rate": _rate(rejected),
        "needs_changes_rate": _rate(needs_changes),
        "avg_time_to_first_decision_seconds": _avg(first_decisions),
        "avg_total_review_seconds": _avg(total_reviews),
        "avg_review_iterations": (
            round(sum(iterations) / len(iterations), 2) if iterations else None
        ),
        "queue_size": queue_size,
        "longest_pending": longest_pending,
        "threshold_buckets": threshold_buckets,
    }


# ── Engagement ───────────────────────────────────────────────────────────────


async def compute_engagement(
    session: AsyncSession, filters: AnalyticsFilters, trend_days: int
) -> dict:
    """Interaction totals plus a per-day views-over-time series (app timezone)."""
    event_ids = _filtered_event_ids(filters)

    action_rows = (
        await session.execute(
            select(EventAnalytics.action, func.count())
            .where(EventAnalytics.event_id.in_(event_ids))
            .group_by(EventAnalytics.action)
        )
    ).all()
    counts = {action: count for action, count in action_rows}

    totals = {
        "views": sum(counts.get(a, 0) for a in VIEW_ACTIONS),
        "register_clicks": counts.get(REGISTER_ACTION, 0),
        "share_clicks": counts.get(SHARE_ACTION, 0),
        "reminder_creates": counts.get(REMINDER_CREATE_ACTION, 0),
        "favorites_added": counts.get(FAVORITE_ADD_ACTION, 0),
        "favorites_removed": counts.get(FAVORITE_REMOVE_ACTION, 0),
    }

    views_over_time = await _views_over_time(session, event_ids, trend_days)
    return {"totals": totals, "views_over_time": views_over_time}


async def _views_over_time(session, event_ids, trend_days: int) -> list[dict]:
    tz = _app_tz()
    now_local = _now_utc().astimezone(tz)
    start_local = (now_local - timedelta(days=trend_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_utc = start_local.astimezone(timezone.utc)

    # bucket by calendar day in the app timezone
    day_bucket = func.date(func.timezone(get_settings().app_timezone, EventAnalytics.created_at))
    rows = (
        await session.execute(
            select(day_bucket.label("day"), func.count())
            .where(
                EventAnalytics.event_id.in_(event_ids),
                EventAnalytics.action.in_(VIEW_ACTIONS),
                EventAnalytics.created_at >= start_utc,
            )
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
    ).all()
    by_day = {row.day.isoformat() if hasattr(row.day, "isoformat") else str(row.day): row[1] for row in rows}

    # dense series: fill zero-view days so the client never has to infer gaps
    series = []
    for i in range(trend_days):
        d = (start_local + timedelta(days=i)).date().isoformat()
        series.append({"date": d, "count": by_day.get(d, 0)})
    return series


_TOP_METRICS = {
    "views": VIEW_ACTIONS,
    "registrations": (REGISTER_ACTION,),
    "shares": (SHARE_ACTION,),
    "favorites": (FAVORITE_ADD_ACTION,),
}


async def compute_top_events(
    session: AsyncSession,
    filters: AnalyticsFilters,
    metric: str,
    limit: int,
    offset: int,
) -> list[dict]:
    """Server-side top-N ranking for one engagement metric (paginated)."""
    event_ids = _filtered_event_ids(filters)

    if metric == "rated":
        count_col = func.count().label("value")
        avg_col = func.avg(cast(Rating.score, Float)).label("avg_score")
        stmt = (
            select(Event.id, Event.title, avg_col, count_col)
            .join(Rating, Rating.event_id == Event.id)
            .where(Event.id.in_(event_ids), Rating.deleted_at.is_(None))
            .group_by(Event.id, Event.title)
            .order_by(avg_col.desc(), count_col.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await session.execute(stmt)).all()
        return [
            {
                "event_id": eid,
                "title": title,
                "value": round(float(avg), 2),
                "count": count,
            }
            for eid, title, avg, count in rows
        ]

    actions = _TOP_METRICS.get(metric)
    if actions is None:
        raise ValueError(f"unknown metric {metric!r}")

    value_col = func.count().label("value")
    stmt = (
        select(Event.id, Event.title, value_col)
        .join(EventAnalytics, EventAnalytics.event_id == Event.id)
        .where(Event.id.in_(event_ids), EventAnalytics.action.in_(actions))
        .group_by(Event.id, Event.title)
        .order_by(value_col.desc(), Event.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return [{"event_id": eid, "title": title, "value": value} for eid, title, value in rows]


# ── Ratings ──────────────────────────────────────────────────────────────────


async def compute_ratings(
    session: AsyncSession, filters: AnalyticsFilters, top_limit: int
) -> dict:
    """Average, 1–5 distribution, totals, zero-review count, and top/lowest
    rated events. Soft-deleted ratings (deleted_at) are excluded everywhere."""
    event_ids = _filtered_event_ids(filters)
    active = and_(Rating.event_id.in_(event_ids), Rating.deleted_at.is_(None))

    avg = await session.scalar(select(func.avg(cast(Rating.score, Float))).where(active))
    total_reviews = (await session.scalar(select(func.count()).where(active))) or 0

    dist_rows = (
        await session.execute(
            select(Rating.score, func.count()).where(active).group_by(Rating.score)
        )
    ).all()
    distribution = {str(score): 0 for score in range(1, 6)}
    for score, count in dist_rows:
        distribution[str(score)] = count

    # events (within the filter set) that have no active rating
    total_events = (
        await session.scalar(
            select(func.count()).select_from(Event).where(and_(*filters.event_conditions()))
            if filters.event_conditions()
            else select(func.count()).select_from(Event)
        )
    ) or 0
    rated_events = (
        await session.scalar(
            select(func.count(func.distinct(Rating.event_id))).where(active)
        )
    ) or 0
    events_with_zero_reviews = max(total_events - rated_events, 0)

    avg_col = func.avg(cast(Rating.score, Float)).label("avg_score")
    count_col = func.count().label("review_count")

    async def _ranked(order):
        stmt = (
            select(Event.id, Event.title, avg_col, count_col)
            .join(Rating, Rating.event_id == Event.id)
            .where(active)
            .group_by(Event.id, Event.title)
            .order_by(order, count_col.desc())
            .limit(top_limit)
        )
        rows = (await session.execute(stmt)).all()
        return [
            {"event_id": eid, "title": title, "value": round(float(a), 2), "count": c}
            for eid, title, a, c in rows
        ]

    top_rated = await _ranked(avg_col.desc())
    lowest_rated = await _ranked(avg_col.asc())

    return {
        "average": round(float(avg), 2) if avg is not None else None,
        "distribution": distribution,
        "total_reviews": total_reviews,
        "events_with_zero_reviews": events_with_zero_reviews,
        "top_rated": top_rated,
        "lowest_rated": lowest_rated,
    }


# ── Categories ───────────────────────────────────────────────────────────────


async def compute_categories(
    session: AsyncSession, filters: AnalyticsFilters
) -> list[dict]:
    """Per-category breakdown: event count, views, registration clicks, average
    rating and approval rate — over the filtered event set. Computed with a few
    grouped queries merged in Python (no per-category round trips)."""
    conditions = filters.event_conditions()
    base = and_(*conditions) if conditions else True
    event_ids = _filtered_event_ids(filters)

    approved_case = case((Event.status == EventStatus.APPROVED.value, 1), else_=0)
    cat_rows = (
        await session.execute(
            select(
                EventCategory.id,
                EventCategory.name,
                func.count(Event.id),
                func.coalesce(func.sum(approved_case), 0),
            )
            .join(Event, Event.category_id == EventCategory.id)
            .where(base)
            .group_by(EventCategory.id, EventCategory.name)
        )
    ).all()

    view_rows = (
        await session.execute(
            select(
                Event.category_id,
                func.count().filter(EventAnalytics.action.in_(VIEW_ACTIONS)),
                func.count().filter(EventAnalytics.action == REGISTER_ACTION),
            )
            .join(EventAnalytics, EventAnalytics.event_id == Event.id)
            .where(Event.id.in_(event_ids))
            .group_by(Event.category_id)
        )
    ).all()
    views_by_cat = {cid: (v, r) for cid, v, r in view_rows}

    rating_rows = (
        await session.execute(
            select(Event.category_id, func.avg(cast(Rating.score, Float)))
            .join(Rating, Rating.event_id == Event.id)
            .where(Event.id.in_(event_ids), Rating.deleted_at.is_(None))
            .group_by(Event.category_id)
        )
    ).all()
    rating_by_cat = {cid: avg for cid, avg in rating_rows}

    result = []
    for cid, name, count, approved in cat_rows:
        views, regs = views_by_cat.get(cid, (0, 0))
        avg = rating_by_cat.get(cid)
        result.append(
            {
                "category_id": cid,
                "category": name,
                "event_count": count,
                "views": views or 0,
                "registration_clicks": regs or 0,
                "average_rating": round(float(avg), 2) if avg is not None else None,
                "approval_rate": round(approved / count, 4) if count else 0.0,
            }
        )
    result.sort(key=lambda r: r["event_count"], reverse=True)
    return result


# ── Organizers ───────────────────────────────────────────────────────────────


async def compute_organizers(
    session: AsyncSession,
    filters: AnalyticsFilters,
    limit: int,
    offset: int,
) -> list[dict]:
    """Most-active organizers (paginated) with events created, approval/rejection
    rate, average rating and engagement attributable to their events. Only
    aggregate/attributable figures are exposed — never per-student data."""
    conditions = filters.event_conditions()
    base = and_(*conditions) if conditions else True

    approved_case = case((Event.status == EventStatus.APPROVED.value, 1), else_=0)
    rejected_case = case((Event.status == EventStatus.REJECTED.value, 1), else_=0)

    # page of organizers ranked by activity, with their event-state counts
    org_rows = (
        await session.execute(
            select(
                Event.organizer_name,
                func.count(Event.id).label("events_created"),
                func.coalesce(func.sum(approved_case), 0),
                func.coalesce(func.sum(rejected_case), 0),
            )
            .where(base)
            .group_by(Event.organizer_name)
            .order_by(func.count(Event.id).desc(), Event.organizer_name.asc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    names = [row[0] for row in org_rows]
    if not names:
        return []

    event_ids = _filtered_event_ids(filters)

    eng_rows = (
        await session.execute(
            select(
                Event.organizer_name,
                func.count().filter(EventAnalytics.action.in_(VIEW_ACTIONS)),
                func.count().filter(EventAnalytics.action == REGISTER_ACTION),
            )
            .join(EventAnalytics, EventAnalytics.event_id == Event.id)
            .where(Event.id.in_(event_ids), Event.organizer_name.in_(names))
            .group_by(Event.organizer_name)
        )
    ).all()
    eng_by_org = {name: (v, r) for name, v, r in eng_rows}

    fav_rows = (
        await session.execute(
            select(Event.organizer_name, func.count())
            .join(Favorite, Favorite.event_id == Event.id)
            .where(Event.id.in_(event_ids), Event.organizer_name.in_(names))
            .group_by(Event.organizer_name)
        )
    ).all()
    fav_by_org = {name: count for name, count in fav_rows}

    rating_rows = (
        await session.execute(
            select(Event.organizer_name, func.avg(cast(Rating.score, Float)))
            .join(Rating, Rating.event_id == Event.id)
            .where(
                Event.id.in_(event_ids),
                Event.organizer_name.in_(names),
                Rating.deleted_at.is_(None),
            )
            .group_by(Event.organizer_name)
        )
    ).all()
    rating_by_org = {name: avg for name, avg in rating_rows}

    result = []
    for name, events_created, approved, rejected in org_rows:
        views, regs = eng_by_org.get(name, (0, 0))
        avg = rating_by_org.get(name)
        result.append(
            {
                "organizer": name,
                "events_created": events_created,
                "approval_rate": round(approved / events_created, 4)
                if events_created
                else 0.0,
                "rejection_rate": round(rejected / events_created, 4)
                if events_created
                else 0.0,
                "average_rating": round(float(avg), 2) if avg is not None else None,
                "views": views or 0,
                "registration_clicks": regs or 0,
                "favorites": fav_by_org.get(name, 0),
            }
        )
    return result


# ── Per-event moderation detail ──────────────────────────────────────────────


async def compute_event_moderation_detail(
    session: AsyncSession, event_id: int
) -> dict | None:
    """Exact moderation timeline for a single event.

    Returns None if the event does not exist. Never aggregates — every value
    is the actual timestamp or count for this event's history.
    """
    CreatorUser = User.__table__.alias("creator_user")
    event_row = (
        await session.execute(
            select(Event.status, Event.created_at, CreatorUser.c.first_name)
            .outerjoin(CreatorUser, Event.creator_user_id == CreatorUser.c.id)
            .where(Event.id == event_id)
        )
    ).first()
    if event_row is None:
        return None

    status, event_created_at, creator_first_name = event_row

    ActorUser = User.__table__.alias("actor_user")
    log_rows = (
        await session.execute(
            select(
                ModerationLog.action,
                ModerationLog.comment,
                ModerationLog.created_at,
                ModerationLog.actor_user_id,
                ActorUser.c.first_name,
            )
            .outerjoin(ActorUser, ModerationLog.actor_user_id == ActorUser.c.id)
            .where(ModerationLog.event_id == event_id)
            .order_by(ModerationLog.created_at.asc(), ModerationLog.id.asc())
        )
    ).all()

    entries = [_LogEntry(action=r.action, created_at=r.created_at) for r in log_rows]
    # note: r.first_name is now the actor's name (column index 4); r.actor_user_id is index 3
    submitted_at = _submission_start(entries, event_created_at)

    first_reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    for r in log_rows:
        if r.action in _DECISION_ACTIONS and first_reviewed_at is None:
            first_reviewed_at = r.created_at
        if r.action in (ModerationAction.APPROVED.value, ModerationAction.RESTORED.value) and approved_at is None:
            approved_at = r.created_at
        if r.action == ModerationAction.REJECTED.value and rejected_at is None:
            rejected_at = r.created_at

    tr = total_review_seconds(entries, event_created_at)
    iterations = review_iterations(entries) or 0
    needs_changes_count = sum(
        1 for r in log_rows if r.action == ModerationAction.NEEDS_CHANGES.value
    )
    resubmission_count = sum(
        1 for r in log_rows if r.action == ModerationAction.RESUBMITTED.value
    )

    latest_moderator: str | None = None
    latest_comment: str | None = None
    for r in reversed(log_rows):
        if r.action in _DECISION_ACTIONS and latest_moderator is None:
            latest_moderator = r.first_name
        if r.comment and latest_comment is None:
            latest_comment = r.comment
        if latest_moderator is not None and latest_comment is not None:
            break

    last_status_update = log_rows[-1].created_at if log_rows else None

    def _fmt(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt is not None else None

    _CREATOR_ACTIONS = frozenset((ModerationAction.SUBMITTED.value, ModerationAction.RESUBMITTED.value))
    history = [
        {
            "action": r.action,
            # Only show a name for submission entries (who submitted/resubmitted).
            # Coordinator decision rows (approved, rejected, needs_changes, etc.)
            # carry no name — the action and comment are sufficient.
            "actor_name": (
                r.first_name or creator_first_name
                if r.action in _CREATOR_ACTIONS
                else None
            ),
            "comment": r.comment,
            "created_at": _fmt(r.created_at),
        }
        for r in log_rows
    ]

    return {
        "current_status": status,
        "submitted_at": _fmt(submitted_at),
        "first_reviewed_at": _fmt(first_reviewed_at),
        "approved_at": _fmt(approved_at),
        "rejected_at": _fmt(rejected_at),
        "total_review_seconds": tr,
        "review_iterations": iterations,
        "needs_changes_count": needs_changes_count,
        "resubmission_count": resubmission_count,
        "latest_moderator": latest_moderator,
        "latest_comment": latest_comment,
        "last_status_update": _fmt(last_status_update),
        "creator_resubmitted": resubmission_count > 0,
        "history": history,
    }


# ── Per-event reviews ────────────────────────────────────────────────────────


async def compute_event_reviews(
    session: AsyncSession, event_id: int, limit: int, offset: int
) -> list[dict]:
    """Paginated reviews (rating + optional comment) for a single event.

    Only non-deleted ratings are included. Comments are outer-joined so a
    rating without a review text still appears. Results are newest-first.
    """
    rows = (
        await session.execute(
            select(
                Rating.id,
                Rating.user_id,
                Rating.score,
                Rating.created_at,
                User.first_name,
                User.username,
                User.photo_url,
                User.telegram_id,
                User.photo_updated_at,
                Comment.content,
            )
            .join(User, User.id == Rating.user_id)
            .outerjoin(
                Comment,
                and_(
                    Comment.user_id == Rating.user_id,
                    Comment.event_id == Rating.event_id,
                    Comment.deleted_at.is_(None),
                ),
            )
            .where(Rating.event_id == event_id, Rating.deleted_at.is_(None))
            .order_by(Rating.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return [
        {
            "rating_id": r.id,
            "user_id": r.user_id,
            "display_name": r.first_name or f"User {r.user_id}",
            "username": r.username,
            "photo_url": _resolve_avatar_url(
                r.photo_url, r.telegram_id, r.photo_updated_at
            ),
            "score": r.score,
            "content": r.content,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def _resolve_avatar_url(
    photo_url: str | None,
    telegram_id: int | None,
    photo_updated_at: datetime | None,
) -> str | None:
    """Mirror the Mini App's avatar resolution: prefer a stored Telegram photo
    URL, otherwise fall back to the backend avatar proxy keyed by telegram_id so
    users without a cached photo_url still get their picture."""
    if photo_url:
        return photo_url
    if telegram_id and telegram_id > 0:
        version = (
            photo_updated_at.isoformat() if photo_updated_at else str(telegram_id)
        )
        return f"/api/events/avatar/{telegram_id}?{urlencode({'v': version})}"
    return None


# ── Event picker search ──────────────────────────────────────────────────────


async def search_events(
    session: AsyncSession,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> list[dict]:
    """Paginated event search for the analytics event-picker.

    Returns every status (approved/archived/cancelled/…) so a coordinator can
    inspect analytics for any event, and only the fields the picker renders —
    never per-user identifying data. Title search is a case-insensitive prefix/
    substring match, driven server-side so the client never downloads all events.
    """
    stmt = (
        select(
            Event.id,
            Event.title,
            EventCategory.name.label("category"),
            Event.event_date,
            Event.status,
        )
        .join(EventCategory, EventCategory.id == Event.category_id)
    )
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(func.lower(Event.title).like(func.lower(term)))
    stmt = (
        stmt.order_by(Event.event_date.desc(), Event.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "category": row.category,
            "event_date": row.event_date.isoformat(),
            "status": row.status,
        }
        for row in rows
    ]
