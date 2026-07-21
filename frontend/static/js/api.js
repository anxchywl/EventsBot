import { authHeaders, setSession, state } from "./state.js?v=20260721-timeline-v7";
import { initData } from "./telegram.js?v=20260721-timeline-v7";

let authInFlight = null;

// send api requests with session headers
export async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(path, {
      ...options,
      signal: options.signal || controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(options.headers || {}),
      },
    }).finally(() => window.clearTimeout(timeout));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload?.detail || payload?.message || "Request failed");
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  } catch (error) {
    window.clearTimeout(timeout);
    if (error.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw error;
  }
}

// create a session from telegram init data
export async function authenticate({ force = false } = {}) {
  if (!force && state.session && state.user) {
    return { token: state.session, user: state.user };
  }
  if (authInFlight) {
    return authInFlight;
  }
  const data = initData();
  if (!data) {
    return null;
  }

  authInFlight = (async () => {
    const payload = await request("/api/auth/session", {
      method: "POST",
      body: JSON.stringify({ initData: data }),
    });
    setSession(payload.token, payload.user);
    return payload;
  })();

  try {
    return await authInFlight;
  } finally {
    authInFlight = null;
  }
}

// load event feed data with active filters
export async function fetchEvents(filters = {}) {
  const events = [];
  const pageSize = 200;
  for (let offset = 0; offset <= 5000; offset += pageSize) {
    const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
    if (filters.sort) params.set("sort", filters.sort);
    if (filters.relevance) params.set("relevance", filters.relevance);
    if (filters.categories?.length) params.set("categories", filters.categories.join(","));
    if (filters.organizers?.length) params.set("organizers", filters.organizers.join(","));
    if (filters.locations?.length) params.set("locations", filters.locations.join(","));
    if (filters.favoritesOnly) params.set("favorite_only", "true");
    const page = await request(`/api/events?${params.toString()}`);
    events.push(...page);
    if (page.length < pageSize) break;
  }
  return events;
}

// load event filter options
export function fetchEventFilters() {
  return request("/api/events/filters");
}

// check whether cached events are stale
export function fetchEventSyncVersion() {
  return request("/api/events/sync-version");
}

export function createStreamTicket() {
  return request("/api/events/stream-ticket", { method: "POST" });
}

// load one event by public token
export async function fetchEvent(token) {
  return request(`/api/events/${encodeURIComponent(token)}`);
}

// save one event for the current user
export function addFavorite(token) {
  return request(`/api/events/${encodeURIComponent(token)}/favorite`, { method: "POST" });
}

// remove one saved event for the current user
export function removeFavorite(token) {
  return request(`/api/events/${encodeURIComponent(token)}/favorite`, { method: "DELETE" });
}

// load scheduled reminders for the current user
export function fetchReminders() {
  return request("/api/reminders");
}

// create or replace one event reminder
export function createReminder(token, offsetMinutes) {
  return request(`/api/events/${encodeURIComponent(token)}/reminders`, {
    method: "POST",
    body: JSON.stringify({ offset_minutes: offsetMinutes }),
  });
}

// delete one scheduled reminder
export function deleteReminder(reminderId) {
  return request(`/api/reminders/${encodeURIComponent(reminderId)}`, { method: "DELETE" });
}

// request share metadata for one event
export function shareEvent(token) {
  return request(`/api/events/${encodeURIComponent(token)}/share`, { method: "POST" });
}

// record event registration intent
export function registerEvent(token) {
  return request(`/api/events/${encodeURIComponent(token)}/register`, { method: "POST" });
}

// account and profile endpoints
export function register(email, password) {
  return request("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

// complete email verification
export async function verifyCode(email, code) {
  const payload = await request("/api/auth/verify", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });
  setSession(payload.token, payload.user);
  return payload;
}

// resend email verification code
export function resendCode(email) {
  return request("/api/auth/resend", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

// link email account to current telegram identity
export async function login(email, password) {
  const payload = await request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setSession(payload.token, payload.user);
  return payload;
}

// load profile history and social state
export function fetchProfile() {
  return request("/api/auth/profile");
}

// update public profile nickname
export function updateNickname(nickname) {
  return request("/api/auth/profile/nickname", {
    method: "PUT",
    body: JSON.stringify({ nickname }),
  });
}

// unlink current telegram session from profile
export async function logout() {
  await request("/api/auth/profile/logout", { method: "POST" }).catch(() => null);
  setSession("", null);
  await authenticate();
}

// call reset endpoints before a verified email session exists
export function forgotPasswordRequest(email) {
  return request("/api/auth/forgot-password/request", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

// verify reset code before showing new password fields
export function forgotPasswordVerify(email, code) {
  return request("/api/auth/forgot-password/verify", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });
}

// consume reset code and update password
export function forgotPasswordReset(email, code, newPassword) {
  return request("/api/auth/forgot-password/reset", {
    method: "POST",
    body: JSON.stringify({ email, code, new_password: newPassword }),
  });
}

// review and rating endpoints
export function submitReview(token, score, content) {
  return request(`/api/events/${encodeURIComponent(token)}/reviews`, {
    method: "POST",
    body: JSON.stringify({ score, content }),
  });
}

// delete current user review for one event
export function deleteReview(token) {
  return request(`/api/events/${encodeURIComponent(token)}/reviews`, {
    method: "DELETE",
  });
}

// delete review through admin endpoint
export function adminDeleteReview(userId, eventToken) {
  return request(`/api/events/admin/${encodeURIComponent(eventToken)}/reviews/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

// load reviews for one event
export function fetchReviews(token) {
  return request(`/api/events/${encodeURIComponent(token)}/reviews`);
}

// load current friend list for profile views
export function fetchFriends() {
  return request("/api/friends");
}

// load incoming and outgoing friend requests
export function fetchFriendRequests() {
  return request("/api/friends/requests");
}

// send a direct friend request by user id
export function sendFriendRequest(userId) {
  return request("/api/friends/requests", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

// accept an invite by sending its owner a request
export function sendInviteFriendRequest(inviteToken) {
  return request("/api/friends/requests", {
    method: "POST",
    body: JSON.stringify({ invite_token: inviteToken }),
  });
}

// accept an incoming friend request
export function acceptFriendRequest(requestId) {
  return request(`/api/friends/requests/${encodeURIComponent(requestId)}/accept`, { method: "POST" });
}

// decline an incoming friend request
export function declineFriendRequest(requestId) {
  return request(`/api/friends/requests/${encodeURIComponent(requestId)}/decline`, { method: "POST" });
}

// cancel an outgoing friend request
export function cancelFriendRequest(requestId) {
  return request(`/api/friends/requests/${encodeURIComponent(requestId)}/cancel`, { method: "POST" });
}

// remove an existing friendship
export function removeFriend(userId) {
  return request(`/api/friends/${encodeURIComponent(userId)}`, { method: "DELETE" });
}

// search verified users who allow requests
export function searchFriends(query, page = 1, limit = 20) {
  const params = new URLSearchParams({ q: query, page: String(page), limit: String(limit) });
  return request(`/api/friends/search?${params.toString()}`);
}

// create a shareable friend invite link
export function createFriendInvite() {
  return request("/api/friends/invites", { method: "POST" });
}

// resolve friend invite state for the current user
export function fetchFriendInvite(token) {
  return request(`/api/friends/invites/${encodeURIComponent(token)}`);
}

// revoke an active friend invite link
export function revokeFriendInvite(inviteId) {
  return request(`/api/friends/invites/${encodeURIComponent(inviteId)}`, { method: "DELETE" });
}

// load friend privacy preferences
export function fetchPrivacySettings() {
  return request("/api/friends/settings");
}

// update friend privacy preferences
export function updatePrivacySettings(settings) {
  return request("/api/friends/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}
