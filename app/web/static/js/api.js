import { authHeaders, setSession } from "./state.js";
import { initData } from "./telegram.js";

async function request(path, options = {}) {
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
  const payload = await request("/api/auth/session", {
    method: "POST",
    body: JSON.stringify({ initData: data }),
  });
  setSession(payload.token, payload.user);
  return payload;
}

export function fetchEvents() {
  return request("/api/events");
}

export function fetchEvent(token) {
  return request(`/api/events/${encodeURIComponent(token)}`);
}

export function fetchFavorites() {
  return request("/api/favorites");
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
