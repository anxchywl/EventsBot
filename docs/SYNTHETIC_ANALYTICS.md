# Synthetic analytics data

`scripts/generate_synthetic_analytics.py` creates a deterministic analytics dataset from the current public NU event catalogue. It imports public event titles, descriptions, dates, times, organization names, locations, registration links, and cover-image URLs from the catalogue and each event's structured metadata. It does not import contact emails, phone numbers, or named contact people. Generated users, emails, usernames, and request IDs use a seed-derived namespace that is not exposed in event content.

The catalogue is merged from the NU upcoming, trending, and past feeds. Events are deduplicated by canonical URL, normalized title, and cover image. A linked page is accepted only when it contains valid schema.org `Event` metadata, which prevents navigation and footer headings from becoming events. Past source dates are deterministically rebased into the current/upcoming window while preserving the source descriptions, organizations, locations, links, images, and event times.

The command requires an explicit database URL and refuses production-like URLs by default:

```bash
python scripts/generate_synthetic_analytics.py \
  --database-url postgresql+asyncpg://events_bot:events_bot@localhost:54320/events_bot \
  --seed 20260721
```

Preview counts without writing:

```bash
python scripts/generate_synthetic_analytics.py --database-url "$TEST_DATABASE_URL" --dry-run
```

The output includes the dataset key. Rerunning the same seed is idempotent. Remove only that dataset with:

```bash
python scripts/generate_synthetic_analytics.py \
  --database-url "$TEST_DATABASE_URL" \
  --cleanup-key 0123456789ab
```

The cleanup key must be copied from the generator output. Cleanup deletes only users whose email and events whose request ID contain that exact key, then their dependent analytics, favorites, reminders, reviews, comments, moderation logs, and synthetic categories. It does not use broad table truncation.

The generator supports event analytics actions already stored by the application: opens, shared opens, registration clicks, shares, favorite/reminder actions, and reminder clicks. Search/filter/attendance analytics have no corresponding database model and are not generated.
