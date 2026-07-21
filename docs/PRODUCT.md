# Student Events Product Specification

Canonical product behavior and business rules. Infrastructure belongs in [INFRASTRUCTURE.md](./INFRASTRUCTURE.md); the public system map is in [README.md](../README.md).

## Product surfaces

- **Telegram Mini App:** student discovery, event details, favorites, registration links, sharing, reminders, reviews, friends, privacy settings, and the web admin area.
- **Flutter standalone development host:** coordinator event creation, ownership-based management, requested changes, published-event update drafts, and administrator moderation.
- **Telegram bot:** group connection, permission checks, category selection, dashboard recreation, and dashboard event pages.
- **Background services:** reminder delivery and PostgreSQL-backed event synchronization to Telegram.

Event submission and moderation bot routers exist in the source tree but are not registered by the current bot startup. Flutter is the active management surface.

The Flutter feature is not integrated with Jas Wallet. Standalone developer authentication remains the current development state. The dormant host-token bridge is future-facing and must not be enabled until the Jas Wallet contract is verified.

## Roles and identity

- A Telegram user exchanges fresh, correctly signed Telegram `initData` for a revocable Mini App session.
- A university-email user registers with an `@nu.edu.kz` address, verifies that same stored address, and signs in with a password.
- Telegram and email credentials resolve to one user record when linked through supported flows.
- Standalone Flutter native authentication is accepted only when `FLUTTER_NATIVE_AUTH_ENABLED=true` and `LOG_LEVEL=DEBUG`.
- Regular users can mutate only their own event drafts, reviews, friendships, reminders, favorites, and profile settings.
- Administrator access is determined on the server. Client-provided role values are never authoritative.
- Logout revokes the current session. Password reset revokes existing sessions for the account.

Verification and reset codes are single-use, expire after their configured TTL, and are bound to their intended account. Resending a verification code must not redirect a code to a different address. Authentication delivery failures must be visible to the requesting client; production email must use configured SMTP rather than console delivery.

## Event lifecycle

```text
create -> pending -> approved
                  -> rejected
                  -> needs_changes -> resubmitted -> approved/rejected/needs_changes

approved edit -> new pending child draft -> approved merge or rejected draft
approved/pending/needs_changes/resubmitted -> cancelled -> deleted retirement
rejected -> deleted retirement
```

Rules:

- Creation and resubmission accept a client request ID. Repeating the same request with the same payload returns the existing result; reusing the ID for a different payload is rejected.
- A cover reference is short-lived, owned by one user, atomically single-use, and redeemed before an event mutation commits.
- Event dates, times, and location overlaps are validated on the server in `Asia/Almaty`. End time must be after start time on the same event date.
- Events whose end time has passed cannot be approved.
- Only approved, non-deleted events are public in the Mini App, direct detail routes, registration links, Telegram pages, and dashboards.
- Editing an approved event creates a child draft. The published parent stays visible until an administrator approves the draft, then the draft is merged into the parent and retired.
- Rejected or cancelled events are unpublished. Scheduled reminders are cancelled when an event is rejected, cancelled, or deleted.
- Deletion is a soft retirement, not a database hard delete. Moderation, audit, and analytics history remains available for authorized reporting.
- Concurrent moderator decisions are serialized. A stale second decision receives a conflict response and cannot overwrite the first result silently.
- Event changes create durable synchronization jobs in the same database transaction as the state mutation.

## Student event interactions

- Search and filters operate only on approved events and support bounded pagination.
- Opening an event records an interaction. A user may review only an approved event they have interacted with.
- One user has at most one rating and one comment per event; a later submission updates that review.
- Favorites, reminder creation, registration clicks, shares, and attendance analytics are server-authoritative.
- Reminder creation rejects unavailable or ended events and prevents duplicates for the same event and offset.
- A registration click is recorded before the user is sent to the stored HTTPS URL. If an organizer's external URL later fails, the application can report the click but cannot guarantee the third-party site remains available.
- Notifications and deep links targeting a deleted, rejected, or inaccessible event must resolve to an unavailable state without exposing event content.

## Friends and privacy

- A user can search visible profiles, send, accept, decline, or cancel requests, remove friends, and create or revoke invite links.
- A canonical database lock serializes actions for a user pair. Opposite-direction requests cannot create duplicate friendships or contradictory pending requests.
- Invite tokens are unguessable bearer links. Anyone holding a valid unrevoked link can claim it; the owner must revoke a link that was shared unintentionally. The product does not promise recipient-bound public invites.
- `show_profile_to_friends=false` hides the profile from search and returns a restricted public summary to other users.
- Friend-list visibility supports public, friends-only, and private.
- Attendance visibility is enforced on the server before friend attendance data is returned.
- Friend and request collections are bounded and paginated.

## Telegram groups and dashboards

- One `dashboard_messages` row exists per connected chat.
- A group must grant the bot the required edit/delete permissions; pin permission is tracked separately because Telegram chat types differ.
- Category filters determine which approved events appear in each dashboard.
- An event mutation enqueues a durable sync job; the worker updates event pages and schedules dashboard refreshes.
- A manually deleted dashboard is recreated on the next refresh or by `/dashboard` and the stored message ID is replaced.
- Loss of bot membership deactivates the chat. A pin failure records `can_pin_messages=false` and remains observable without discarding the newly sent dashboard.
- Sync jobs use database claiming and a five-minute processing lease so multiple application instances do not process an active job simultaneously. An expired lease is returned to pending after a worker crash.
- Telegram delivery is at-least-once. A crash after Telegram accepts a request but before the database acknowledgement can produce a duplicate message; reconciliation must use stored message IDs and subsequent refreshes.

## Reminders and realtime state

- Due reminders are claimed with row locking and `SKIP LOCKED`, allowing multiple workers without sending the same actively claimed row concurrently.
- Successful deliveries become `sent`; terminal delivery failures become `failed`; event retirement cancels scheduled reminders.
- A process crash after Telegram accepts a reminder but before the transaction commits can still cause a duplicate delivery. This is an external acknowledgement boundary, not an exactly-once guarantee.
- The Mini App compares a database-backed sync version and listens for SSE updates.
- SSE connections use short-lived, one-time stream tickets rather than placing long-lived session tokens in URLs.
- Reconnect creates a new ticket and triggers normal refresh/version reconciliation, so missed or duplicate signals do not become the source of truth.
- Flutter clears session-scoped private cache when identity changes or a session expires and refetches server-authoritative state after mutations.

## Append-only records

- `event_analytics`, `moderation_logs`, and `audit_logs` are application-level append-only records.
- Event retirement must not cascade-delete these records.
- Administrative deletion of a review is a moderated soft deletion where supported; the associated audit record is retained.
- Analytics counters are derived from recorded actions and must not be treated as authentication or authorization evidence.

## Required edge-case outcomes

| Case | Required outcome |
|---|---|
| Approval after event end | Reject the transition; the event stays unpublished. |
| Edit approved event | Keep the published parent visible; moderate a separate child draft. |
| Bot loses admin permissions | Record degraded permissions or deactivate the chat, retry safely, and expose the condition to admins. |
| Dashboard message manually deleted | Recreate it, store the replacement ID, and attempt to pin it. |
| Two administrators moderate one event | Serialize with the database lock; the stale action receives `409 Conflict`. |
| Reminder belongs to rejected/deleted event | Cancel it before delivery. |
| Notification targets unavailable event | Show unavailable/not found without private event data. |
| Registration link fails after publication | Preserve application state and show recoverable navigation; external availability is not guaranteed. |
| Verification/reset code replay | Reject after first successful use. |
| Opposite-direction friend requests | Resolve under one pair lock without duplicate requests or friendships. |
| Public invite claimed by unintended user | Claim is valid for the bearer; owner can revoke unused links. Recipient-bound invites are not promised. |
| Creation/resubmission timeout and retry | Same request ID and payload returns the existing event; a changed payload conflicts. |
| Repeated staged cover token | Only one atomic redemption succeeds. |
| Same-day timezone boundary | Validate and render using `Asia/Almaty`. |
| SSE disconnect during transition | Reconnect with a new ticket and reconcile from sync version/API state. |
| Worker crash after Telegram action | Accept possible duplicate delivery; reconcile on later refresh using stored state. |
| Account switch with cached data | Remove session-scoped private cache before rendering the next account. |
| Multiple sync workers | Claim jobs with row locks and recover only expired processing leases. |

## Primary API groups

| Prefix | Purpose |
|---|---|
| `/api/auth` | Telegram session exchange, university email auth, profile, logout, verification, and reset |
| `/api/events` | approved discovery, details, interactions, reviews, sync version, and stream tickets/SSE |
| `/api/favorites` | current user's favorites |
| `/api/reminders` | current user's reminders |
| `/api/friends` | friend relationships, requests, invites, privacy, and attendance |
| `/api/admin` | server-authorized administration, moderation support, groups, stats, and audit logs |
| `/api/flutter/auth` | Flutter session resolution and debug-only standalone native auth |
| `/api/flutter/events` | coordinator event lifecycle and administrator moderation |
| `/api/flutter/analytics` | authorized event analytics |
| `/health`, `/health/ready` | liveness and dependency readiness |

## Durable data ownership

PostgreSQL is the source of truth for users, roles, events, moderation, chats, dashboards, favorites, reminders, reviews, analytics, friendships, privacy, and sync jobs. Redis data is disposable support state: sessions, rate limits, caches, SSE pub/sub, and staged cover bytes/tokens. Telegram message IDs stored in PostgreSQL link durable application state to external Telegram messages.
