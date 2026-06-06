import { authHeaders, setSession } from "./state.js?v=20260607-cal-v2";
import { initData } from "./telegram.js?v=20260607-cal-v2";

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

export async function authenticate() {
  const data = initData();
  if (!data) {
    return null;
  }
  try {
    const payload = await request("/api/auth/session", {
      method: "POST",
      body: JSON.stringify({ initData: data }),
    });
    setSession(payload.token, payload.user);
    return payload;
  } catch (error) {
    setSession("", null);
    throw error;
  }
}

export async function fetchEvents(filters = {}) {
  const params = new URLSearchParams();
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.relevance) params.set("relevance", filters.relevance);
  if (filters.categories?.length) params.set("categories", filters.categories.join(","));
  if (filters.organizers?.length) params.set("organizers", filters.organizers.join(","));
  if (filters.locations?.length) params.set("locations", filters.locations.join(","));
  if (filters.favoritesOnly) params.set("favorite_only", "true");
  const query = params.toString();
  return request(`/api/events${query ? `?${query}` : ""}`);
}

export function fetchEventFilters() {
  return request("/api/events/filters");
}

export function fetchEventSyncVersion() {
  return request("/api/events/sync-version");
}

export async function fetchEvent(token) {
  return request(`/api/events/${encodeURIComponent(token)}`);
}

export function addFavorite(token) {
  return request(`/api/events/${encodeURIComponent(token)}/favorite`, { method: "POST" });
}

export function removeFavorite(token) {
  return request(`/api/events/${encodeURIComponent(token)}/favorite`, { method: "DELETE" });
}

export function fetchReminders() {
  return request("/api/reminders");
}

export function createReminder(token, offsetMinutes) {
  return request(`/api/events/${encodeURIComponent(token)}/reminders`, {
    method: "POST",
    body: JSON.stringify({ offset_minutes: offsetMinutes }),
  });
}

export function deleteReminder(reminderId) {
  return request(`/api/reminders/${encodeURIComponent(reminderId)}`, { method: "DELETE" });
}

export function shareEvent(token) {
  return request(`/api/events/${encodeURIComponent(token)}/share`, { method: "POST" });
}

export function registerEvent(token) {
  return request(`/api/events/${encodeURIComponent(token)}/register`, { method: "POST" });
}

// auth and profile APIs
export function register(email, password) {
  return request("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function verifyCode(email, code) {
  const payload = await request("/api/auth/verify", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });
  setSession(payload.token, payload.user);
  return payload;
}

export function resendCode(email) {
  return request("/api/auth/resend", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function login(email, password) {
  const payload = await request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setSession(payload.token, payload.user);
  return payload;
}

export function fetchProfile() {
  return request("/api/auth/profile");
}

export function updateNickname(nickname) {
  return request("/api/auth/profile/nickname", {
    method: "PUT",
    body: JSON.stringify({ nickname }),
  });
}

export async function logout() {
  await request("/api/auth/profile/logout", { method: "POST" }).catch(() => null);
  setSession("", null);
  await authenticate();
}

// forgot-password APIs (unauthenticated — no miniapp auth header needed for these)
export function forgotPasswordRequest(email) {
  return request("/api/auth/forgot-password/request", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function forgotPasswordVerify(email, code) {
  return request("/api/auth/forgot-password/verify", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });
}

export function forgotPasswordReset(email, code, newPassword) {
  return request("/api/auth/forgot-password/reset", {
    method: "POST",
    body: JSON.stringify({ email, code, new_password: newPassword }),
  });
}

// ratings and reviews APIs
export function submitReview(token, score, content) {
  return request(`/api/events/${encodeURIComponent(token)}/reviews`, {
    method: "POST",
    body: JSON.stringify({ score, content }),
  });
}

export function deleteReview(token) {
  return request(`/api/events/${encodeURIComponent(token)}/reviews`, {
    method: "DELETE",
  });
}

export function adminDeleteReview(userId, eventToken) {
  return request(`/api/events/admin/${encodeURIComponent(eventToken)}/reviews/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

export function fetchReviews(token) {
  return request(`/api/events/${encodeURIComponent(token)}/reviews`);
}

export function fetchFriends() {
  return request("/api/friends");
}

export function fetchFriendRequests() {
  return request("/api/friends/requests");
}

export function sendFriendRequest(userId) {
  return request("/api/friends/requests", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function sendInviteFriendRequest(inviteToken) {
  return request("/api/friends/requests", {
    method: "POST",
    body: JSON.stringify({ invite_token: inviteToken }),
  });
}

export function acceptFriendRequest(requestId) {
  return request(`/api/friends/requests/${encodeURIComponent(requestId)}/accept`, { method: "POST" });
}

export function declineFriendRequest(requestId) {
  return request(`/api/friends/requests/${encodeURIComponent(requestId)}/decline`, { method: "POST" });
}

export function cancelFriendRequest(requestId) {
  return request(`/api/friends/requests/${encodeURIComponent(requestId)}/cancel`, { method: "POST" });
}

export function removeFriend(userId) {
  return request(`/api/friends/${encodeURIComponent(userId)}`, { method: "DELETE" });
}

export function searchFriends(query, page = 1, limit = 20) {
  const params = new URLSearchParams({ q: query, page: String(page), limit: String(limit) });
  return request(`/api/friends/search?${params.toString()}`);
}

export function createFriendInvite() {
  return request("/api/friends/invites", { method: "POST" });
}

export function fetchFriendInvite(token) {
  return request(`/api/friends/invites/${encodeURIComponent(token)}`);
}

export function revokeFriendInvite(inviteId) {
  return request(`/api/friends/invites/${encodeURIComponent(inviteId)}`, { method: "DELETE" });
}

export function fetchPrivacySettings() {
  return request("/api/friends/settings");
}

export function updatePrivacySettings(settings) {
  return request("/api/friends/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}
