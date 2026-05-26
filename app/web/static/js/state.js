const STORED_LANG = "events_miniapp_lang";
const STORED_THEME = "events_miniapp_theme";
const STORED_SESSION = "events_miniapp_session";

export const LANGS = ["en", "ru", "kk"];

export const state = {
  route: "events",
  token: "",
  session: localStorage.getItem(STORED_SESSION) || "",
  user: null,
  lang: normalizeLang(localStorage.getItem(STORED_LANG) || navigator.language || "en"),
  theme: localStorage.getItem(STORED_THEME) || "",
  events: [],
  favorites: [],
  reminders: [],
  currentEvent: null,
  scroll: {
    events: 0,
    favorites: 0,
    reminders: 0,
  },
};

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
  if (state.session) {
    localStorage.setItem(STORED_SESSION, state.session);
  }
}

export function authHeaders() {
  return state.session ? { Authorization: `Bearer ${state.session}` } : {};
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
