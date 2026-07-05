"""Coordinator analytics dashboard endpoints.

Admin-only, backend-computed metrics for the Flutter Event Manager screen. Each
panel is its own endpoint so one failing/slow query can never blank the whole
dashboard — the client loads, fails and retries each panel independently.

Filters (date range / category / organizer / status) compose (AND) and are
parsed + bounds-checked once in ``analytics_filters`` so every panel reflects the
same active filter set.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.enums import EventStatus
from app.services import analytics_dashboard as svc
from app.web.cache import TTLCache
from app.web.flutter_auth import require_flutter_admin
from app.web.limiter import check_rate_limit
from app.web.schemas import (
    FlutterAnalyticsEngagement,
    FlutterAnalyticsEventOption,
    FlutterAnalyticsModeration,
    FlutterAnalyticsRankedEvent,
    FlutterAnalyticsRatings,
    FlutterAnalyticsSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flutter/analytics", tags=["flutter-analytics"])

# Short-TTL cache for the heavier, slower-moving aggregations only. Summary and
# moderation are deliberately NOT cached: they must reflect the coordinator's own
# just-made moderation decision on the next refresh (freshness > cache-hit).
_agg_cache = TTLCache(ttl_seconds=30, max_items=256)

_ALLOWED_STATUSES = {s.value for s in EventStatus}
_MAX_TOP_LIMIT = 50
_MAX_THRESHOLDS = 6
_MAX_THRESHOLD_HOURS = 24 * 30  # a month; anything larger is meaningless as a queue SLA
_MIN_TREND_DAYS = 1
_MAX_TREND_DAYS = 366  # up to a full year (e.g. the "This Year" period)


# ── Shared filter dependency (validated + bounded) ───────────────────────────


def analytics_filters(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category_id: int | None = Query(default=None, ge=1),
    organizer: str | None = Query(default=None, max_length=255),
    event_status: str | None = Query(default=None, alias="status", max_length=32),
    event_id: int | None = Query(default=None, ge=1),
) -> svc.AnalyticsFilters:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "date_from must not be after date_to",
        )
    if event_status is not None and event_status not in _ALLOWED_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid status filter"
        )
    return svc.AnalyticsFilters(
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        organizer=organizer.strip() if organizer else None,
        status=event_status,
        event_id=event_id,
    )


def _cache_key(name: str, filters: svc.AnalyticsFilters, *extra: object) -> str:
    return "|".join(
        [
            name,
            str(filters.date_from),
            str(filters.date_to),
            str(filters.category_id),
            filters.organizer or "",
            filters.status or "",
            *[str(e) for e in extra],
        ]
    )


async def _limit(request: Request, user_id: int, bucket: str) -> None:
    # protect the heavier aggregation endpoints from being hammered
    await check_rate_limit(
        f"rate:flutter_analytics:{user_id}:{bucket}",
        60,
        60,
        "Too many analytics requests. Try again shortly.",
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/summary", response_model=FlutterAnalyticsSummary)
async def summary(
    request: Request,
    filters: svc.AnalyticsFilters = Depends(analytics_filters),
    user=Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> FlutterAnalyticsSummary:
    await _limit(request, user.id, "summary")
    metrics = await svc.compute_summary(session, filters)
    return FlutterAnalyticsSummary(metrics=metrics)


@router.get("/moderation", response_model=FlutterAnalyticsModeration)
async def moderation(
    request: Request,
    thresholds: list[int] = Query(default=[24, 48]),
    filters: svc.AnalyticsFilters = Depends(analytics_filters),
    user=Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> FlutterAnalyticsModeration:
    await _limit(request, user.id, "moderation")
    # clamp thresholds: bounded count, positive, within a sane ceiling, deduped
    cleaned = sorted(
        {h for h in thresholds if 0 < h <= _MAX_THRESHOLD_HOURS}
    )[:_MAX_THRESHOLDS]
    if not cleaned:
        cleaned = [24, 48]
    data = await svc.compute_moderation(session, filters, cleaned)
    return FlutterAnalyticsModeration(**data)


@router.get("/engagement", response_model=FlutterAnalyticsEngagement)
async def engagement(
    request: Request,
    trend_days: int = Query(default=30),
    filters: svc.AnalyticsFilters = Depends(analytics_filters),
    user=Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> FlutterAnalyticsEngagement:
    await _limit(request, user.id, "engagement")
    window = min(max(trend_days, _MIN_TREND_DAYS), _MAX_TREND_DAYS)
    key = _cache_key("engagement", filters, window)
    cached = _agg_cache.get(key)
    if cached is None:
        cached = await svc.compute_engagement(session, filters, window)
        _agg_cache.set(key, cached)
    return FlutterAnalyticsEngagement(**cached)


@router.get("/engagement/top", response_model=list[FlutterAnalyticsRankedEvent])
async def engagement_top(
    request: Request,
    metric: str = Query(default="views"),
    limit: int = Query(default=10, ge=1, le=_MAX_TOP_LIMIT),
    offset: int = Query(default=0, ge=0, le=10_000),
    filters: svc.AnalyticsFilters = Depends(analytics_filters),
    user=Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterAnalyticsRankedEvent]:
    await _limit(request, user.id, "engagement_top")
    key = _cache_key("top", filters, metric, limit, offset)
    cached = _agg_cache.get(key)
    if cached is None:
        try:
            cached = await svc.compute_top_events(session, filters, metric, limit, offset)
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown metric {metric!r}"
            )
        _agg_cache.set(key, cached)
    return [FlutterAnalyticsRankedEvent(**row) for row in cached]


@router.get("/ratings", response_model=FlutterAnalyticsRatings)
async def ratings(
    request: Request,
    top_limit: int = Query(default=5, ge=1, le=_MAX_TOP_LIMIT),
    filters: svc.AnalyticsFilters = Depends(analytics_filters),
    user=Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> FlutterAnalyticsRatings:
    await _limit(request, user.id, "ratings")
    key = _cache_key("ratings", filters, top_limit)
    cached = _agg_cache.get(key)
    if cached is None:
        cached = await svc.compute_ratings(session, filters, top_limit)
        _agg_cache.set(key, cached)
    return FlutterAnalyticsRatings(**cached)


@router.get("/events", response_model=list[FlutterAnalyticsEventOption])
async def event_options(
    request: Request,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=_MAX_TOP_LIMIT),
    offset: int = Query(default=0, ge=0, le=100_000),
    user=Depends(require_flutter_admin),
    session: AsyncSession = Depends(get_session),
) -> list[FlutterAnalyticsEventOption]:
    """Paginated, searchable event list feeding the analytics event-picker."""
    await _limit(request, user.id, "events")
    term = (search or "").strip()
    key = f"events|{term.lower()}|{limit}|{offset}"
    cached = _agg_cache.get(key)
    if cached is None:
        cached = await svc.search_events(
            session, search=term or None, limit=limit, offset=offset
        )
        _agg_cache.set(key, cached)
    return [FlutterAnalyticsEventOption(**row) for row in cached]
