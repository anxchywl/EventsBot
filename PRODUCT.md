# Student Events Bot — Product Specification

Internal product and business rules reference. Canonical source of truth for product behavior, flows, and edge cases.

- Public overview: [README.md](./README.md)
- Infrastructure and ops: [INFRASTRUCTURE.md](./INFRASTRUCTURE.md)
- Agent coding rules: [AGENTS.md](./AGENTS.md)

---

## 1. Product Overview

Student communities organize many events. Sharing them through group chats creates noise, and interested students miss things or lose track across conversations.

This project keeps one auto-updating dashboard message per connected Telegram group. Students browse and interact with events through a Telegram Mini App. Clubs submit events through the bot. Moderators approve them from a dedicated chat.

Primary goals:

- Let students authenticate with a university email.
- Let clubs submit and manage events through the bot.
- Let moderators approve, reject, or request changes to events.
- Show approved events in Telegram group dashboards and the Mini App.
- Support favorites, reminders, reviews, and sharing in the Mini App.
- Let students connect with friends and see which friends are attending events.
- Notify users about upcoming events they care about.

---

## 2. Core Features

- Telegram bot built with aiogram 3.
- Event submission flow in private chat.
- Moderation queue — approve, reject, or request changes.
- Editable event cards — poster, title, description, date, time, location, category, registration link.
- One auto-updating dashboard message per connected Telegram group.
- Per-group category filters.
- Telegram Mini App — search, filters, favorites, reminders, sharing, reviews.
- Friends — add friends, see friends going to an event, invite via shareable links, privacy settings.
- NU email registration, login, verification codes, and password reset.
- Event analytics — opens, shares, registrations, favorites, and reminders.
- Admin web panel — users, reviews, stats, connected groups, and audit logs.
- Background reminder sender.
- PostgreSQL migrations with Alembic.

---

## 3. Business Rules

- Only approved events are visible to regular users in dashboards and the Mini App.
- A moderator can approve, reject, or request changes; a request for changes returns the event to the submitter.
- Each connected Telegram group has exactly one dashboard message, pinned and auto-updated on any event change.
- Dashboard content is filtered by the category preferences set for each group.
- A user cannot review an event they have not interacted with unless product policy changes.
- Reminders are scheduled per-user per-event; duplicates must be prevented.
- Analytics events are append-only; they must not be modified or deleted.
- Audit and moderation logs are append-only.
- A Telegram identity and a university email account are linked to one user record.
- Email verification codes and password reset codes expire after the configured TTL.
- Friend requests require explicit acceptance; a friendship is only active after both sides agree.
- Privacy settings control who can see a user's friend list and attendance.
- A user can revoke their own friend invite links at any time.

---

## 4. Edge Cases

- A moderator approves an event after the event date has passed.
- A club edits an event after it has been approved and published.
- A connected group revokes the bot's admin permissions after a dashboard has been created.
- The dashboard message is manually deleted from the group.
- Two moderators act on the same pending event simultaneously.
- A user sets a reminder for an event that is later rejected or deleted.
- A notification points to a deleted or inaccessible event.
- A registration link in an event card becomes invalid after publication.
- An email verification code is reused or replayed.
- A friend request is sent to a user who has already sent one in the other direction.
- A friend invite link is shared publicly and claimed by an unintended user.

---

## 5. Event Submission Flow

1. A club member opens the bot in private chat and runs `/submit_event`.
2. The bot guides the user through providing: title, description, date, time, location, category, registration link, and optional poster image.
3. The completed event is saved with status `pending`.
4. The event appears in the moderation queue.
5. A moderator reviews it in the designated moderation chat.
6. On approval, the event status becomes `approved` and is published.
7. On rejection, the event is marked `rejected` and removed from the queue.
8. On request for changes, the event is returned to the submitter with feedback.
9. After approval, connected group dashboards update automatically.
10. The Mini App shows the event to all users.

---

## 6. Moderation Flow

1. A moderator runs `/moderate` or receives a notification about a pending event.
2. The bot presents the event card with approve, reject, and request-changes options.
3. Approve: event status → `approved`; dashboards and Mini App update.
4. Reject: event status → `rejected`; submitter may be notified.
5. Request changes: event is returned to `draft` state with a feedback message; submitter revises and resubmits.

---

## 7. Dashboard Update Flow

1. An event is approved, edited, or deleted.
2. The backend emits an event change signal.
3. The dashboard service identifies all connected groups whose category filters include this event's category.
4. For each group, the bot edits the pinned dashboard message in-place.
5. If the dashboard message has been deleted, the bot recreates and repins it.

---

## 8. Reminder Flow

1. A user sets a reminder for an event via the Mini App.
2. The reminder is stored with the scheduled send time.
3. A background worker runs at a configured interval and checks for due reminders.
4. For each due reminder, the worker sends a Telegram message to the user.
5. The reminder is marked as sent.
6. If the event is deleted or rejected after the reminder is created, the reminder is cancelled.

---

## 9. Friends Flow

Friend request flow:

1. User A searches for User B or uses a friend invite link.
2. User A sends a friend request.
3. User B receives the request and accepts or declines.
4. On acceptance, a friendship record is created for both users.
5. On decline or cancel, the request is removed.

Invite link flow:

1. A user creates a friend invite link.
2. The link is shared via Telegram or any channel.
3. Another user opens the link and is shown User A's profile with an accept option.
4. On acceptance, a friendship is created.
5. The user can revoke the invite link at any time.

Privacy:

- Users can set their friend list visibility to public, friends-only, or private.
- The friends-going count on an event respects each user's privacy settings.

---

## 10. API Endpoints

The FastAPI backend serves the Mini App and exposes the following endpoints.

**Auth**

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/session` | Create session from Telegram init data |
| POST | `/api/auth/register` | Register with NU email and password |
| POST | `/api/auth/verify` | Verify email code |
| POST | `/api/auth/login` | Login with email and password |
| GET | `/api/auth/profile` | Get current user profile |
| PUT | `/api/auth/profile/nickname` | Update nickname |
| POST | `/api/auth/profile/logout` | Logout (invalidate session) |
| POST | `/api/auth/forgot-password/request` | Request a password reset code |
| POST | `/api/auth/forgot-password/verify` | Verify the reset code |
| POST | `/api/auth/forgot-password/reset` | Set a new password |

**Events**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/events` | List approved events |
| GET | `/api/events/filters` | Get filter options |
| GET | `/api/events/{token}` | Get event details |
| POST | `/api/events/{token}/register` | Record a registration click |
| GET | `/api/favorites` | List favorited events |
| POST | `/api/events/{token}/favorite` | Add a favorite |
| DELETE | `/api/events/{token}/favorite` | Remove a favorite |
| GET | `/api/reminders` | List reminders |
| POST | `/api/events/{token}/reminders` | Create a reminder |
| DELETE | `/api/reminders/{id}` | Delete a reminder |
| POST | `/api/events/{token}/share` | Create a Telegram share link |
| GET | `/api/events/{token}/reviews` | List reviews |
| POST | `/api/events/{token}/reviews` | Create or update a review |
| DELETE | `/api/events/{token}/reviews` | Delete own review |
| GET | `/api/events/reviews/feed` | Global review feed |
| GET | `/api/events/sync-version` | Event cache sync version |
| GET | `/api/events/updates` | Event update stream (SSE) |
| GET | `/api/events/review-updates` | Review update stream (SSE) |

**Friends**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/friends` | List friends |
| GET | `/api/friends/requests` | List incoming and outgoing friend requests |
| POST | `/api/friends/requests` | Send a friend request |
| POST | `/api/friends/requests/{id}/accept` | Accept a friend request |
| POST | `/api/friends/requests/{id}/decline` | Decline a friend request |
| POST | `/api/friends/requests/{id}/cancel` | Cancel a sent friend request |
| DELETE | `/api/friends/{friend_user_id}` | Remove a friend |
| GET | `/api/friends/search` | Search users to add as friends |
| POST | `/api/friends/invites` | Create a friend invite link |
| DELETE | `/api/friends/invites/{invite_id}` | Revoke an invite link |
| GET | `/api/friends/invites/{token}` | Look up an invite by token |
| GET | `/api/friends/settings` | Get privacy settings |
| PUT | `/api/friends/settings` | Update privacy settings |
| GET | `/api/friends/events/{event_id}/friends-going` | List friends attending an event |

**Admin**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/stats` | Overview stats |
| GET | `/api/admin/users` | User list |
| GET | `/api/admin/connected-groups` | Connected group list |
| GET | `/api/admin/audit-logs` | Audit log |
| GET | `/health` | Health check |

---

## 11. Database

| Table | Purpose |
|---|---|
| `users` | Telegram users, email accounts, roles, and blocks |
| `events` | Event content, dates, status, and moderation data |
| `event_categories` | Categories used by filters and dashboards |
| `chats` | Connected Telegram groups |
| `chat_category_settings` | Enabled categories per group |
| `dashboard_messages` | Dashboard message IDs per group |
| `event_detail_messages` | Event card message IDs |
| `favorites` | Saved events per user |
| `reminders` | Scheduled reminder records |
| `ratings` / `comments` | Event reviews |
| `event_analytics` | Opens, shares, registrations, and other event actions |
| `moderation_logs` / `audit_logs` | Admin and moderation history |
| `user_activity_logs` | Per-user activity history |
| `email_verification_codes` / `password_reset_codes` | Auth codes |
| `event_sync_jobs` | Background event sync work |
| `clubs` | Club profiles linked to events |
| `friendships` | Active friend pairs |
| `friend_requests` | Pending friend requests |
| `friend_invites` | Shareable invite links for friend discovery |
| `privacy_settings` | Per-user friend visibility preferences |
