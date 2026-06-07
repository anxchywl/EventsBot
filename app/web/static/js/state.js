const STORED_LANG = "events_miniapp_lang";
const STORED_THEME = "events_miniapp_theme";
const STORED_EVENT_FILTERS = "events_miniapp_event_filters";

const DEFAULT_EVENT_FILTERS = Object.freeze({
  sort: "time_asc",
  relevance: "active",
  categories: [],
  organizers: [],
  locations: [],
  timeOfDay: [],
  favoritesOnly: false,
});

export const LANGS = ["en", "ru", "kk"];

export const state = {
  route: "events",
  token: "",
  session: "",
  user: null,
  lang: normalizeLang(localStorage.getItem(STORED_LANG) || navigator.language || "en"),
  theme: localStorage.getItem(STORED_THEME) || "",
  events: [],
  eventFilterOptions: {
    categories: [],
    organizers: [],
    locations: [],
  },
  eventFilterOptionsLoaded: false,
  eventFilters: loadEventFilters(),
  eventSearch: {
    active: false,
    query: "",
  },
  favorites: [],
  reminders: [],
  friends: {
    total: 0,
    friends: [],
  },
  friendRequests: {
    incoming: [],
    outgoing: [],
  },
  friendSearch: {
    query: "",
    results: [],
    page: 1,
    hasMore: false,
    loading: false,
  },
  privacySettings: {
    show_favorites_to_friends: true,
    show_profile_to_friends: true,
    allow_friend_requests: true,
  },
  currentFriendInvite: null,
  currentEvent: null,
  calendarState: {
    currentDate: new Date().toISOString(),
    viewMode: "month",
    selectedEventId: null,
  },
  calendarMode: false,
  scroll: {
    events: 0,
    favorites: 0,
    reminders: 0,
    calendar: 0,
  },

  // forgot-password flow state
  forgotStep: null,         // null | "email" | "code" | "newpwd"
  forgotEmail: "",
  forgotCode: "",
  forgotResendCooldown: 0,

  // preserved error messages on language/theme toggle
  authErrorMsg: "",
  forgotErrorMsg: "",
  nicknameErrorMsg: "",
};

export function defaultEventFilters() {
  return {
    sort: DEFAULT_EVENT_FILTERS.sort,
    relevance: DEFAULT_EVENT_FILTERS.relevance,
    categories: [],
    organizers: [],
    locations: [],
    timeOfDay: [],
    favoritesOnly: false,
  };
}

export function loadEventFilters() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORED_EVENT_FILTERS) || "{}");
    return normalizeEventFilters(parsed);
  } catch {
    return defaultEventFilters();
  }
}

export function normalizeEventFilters(filters = {}) {
  const next = defaultEventFilters();
  if (typeof filters.sort === "string" && filters.sort) {
    next.sort = filters.sort;
  }
  if (typeof filters.relevance === "string" && filters.relevance) {
    next.relevance = filters.relevance;
  }
  next.categories = uniqueStrings(filters.categories);
  next.organizers = uniqueStrings(filters.organizers);
  next.locations = uniqueStrings(filters.locations);
  next.timeOfDay = uniqueStrings(filters.timeOfDay);
  next.favoritesOnly = Boolean(filters.favoritesOnly);
  return next;
}

export function setEventFilters(filters) {
  state.eventFilters = normalizeEventFilters(filters);
  localStorage.setItem(STORED_EVENT_FILTERS, JSON.stringify(state.eventFilters));
  return state.eventFilters;
}

function uniqueStrings(values) {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))].sort();
}

export function normalizeLang(value) {
  const lang = String(value || "en").slice(0, 2).toLowerCase();
  return LANGS.includes(lang) ? lang : "en";
}

export function nextLang() {
  const index = LANGS.indexOf(state.lang);
  setLang(LANGS[(index + 1) % LANGS.length]);
  return state.lang;
}

export function setLang(lang) {
  state.lang = normalizeLang(lang);
  localStorage.setItem(STORED_LANG, state.lang);
  document.documentElement.lang = state.lang;
  const btn = document.querySelector(".lang-toggle");
  if (btn) {
    btn.textContent = state.lang.toUpperCase();
  }
}

export function setTheme(theme) {
  state.theme = theme === "dark" ? "dark" : "light";
  localStorage.setItem(STORED_THEME, state.theme);
  document.documentElement.dataset.theme = state.theme;
}

export function toggleTheme() {
  setTheme(currentTheme() === "dark" ? "light" : "dark");
  return state.theme;
}

export function currentTheme() {
  if (state.theme) {
    return state.theme;
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function setSession(token, user) {
  state.session = token || "";
  state.user = user || null;
}

export function authHeaders() {
  const headers = {};
  if (state.session) {
    headers["Authorization"] = `Bearer ${state.session}`;
  }
  const telegramInitData = window.Telegram?.WebApp?.initData || "";
  if (telegramInitData) {
    headers["X-Telegram-Init-Data"] = telegramInitData;
  }
  headers["X-Language"] = state.lang || "en";
  headers["X-Theme"] = (typeof currentTheme === "function" ? currentTheme() : (state.theme || "light"));
  return headers;
}

export function rememberScroll(route = state.route) {
  if (route in state.scroll) {
    state.scroll[route] = window.scrollY;
  }
}

export function restoreScroll(route = state.route) {
  const y = state.scroll[route] || 0;
  requestAnimationFrame(() => window.scrollTo({ top: y, behavior: "instant" }));
}
