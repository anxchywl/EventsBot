import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadState() {
  vi.resetModules();
  return import("../../frontend/static/js/state.js?v=20260721-timeline-v7");
}

describe("language normalization", () => {
  it("keeps only supported locales and strips region", async () => {
    const { normalizeLang } = await loadState();
    expect(normalizeLang("ru-RU")).toBe("ru");
    expect(normalizeLang("KK")).toBe("kk");
    expect(normalizeLang("en-US")).toBe("en");
    // unsupported locale falls back to english
    expect(normalizeLang("fr")).toBe("en");
    expect(normalizeLang(null)).toBe("en");
  });

  it("cycles languages in a stable order", async () => {
    const { nextLang, setLang, state } = await loadState();
    setLang("en");
    expect(nextLang()).toBe("ru");
    expect(nextLang()).toBe("kk");
    // wraps back around to the start
    expect(nextLang()).toBe("en");
    expect(state.lang).toBe("en");
  });
});

describe("theme toggling", () => {
  it("flips between light and dark and persists the choice", async () => {
    const { setTheme, toggleTheme, currentTheme } = await loadState();
    setTheme("light");
    expect(currentTheme()).toBe("light");
    expect(toggleTheme()).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("events_miniapp_theme")).toBe("dark");
    expect(toggleTheme()).toBe("light");
  });

  it("coerces any non-dark value to light", async () => {
    const { setTheme, currentTheme } = await loadState();
    setTheme("neon");
    expect(currentTheme()).toBe("light");
  });
});

describe("event filter defaults and persistence", () => {
  it("default filters use the configured sort and empty selections", async () => {
    const { defaultEventFilters } = await loadState();
    expect(defaultEventFilters()).toEqual({
      sort: "time_asc",
      relevance: "active",
      categories: [],
      organizers: [],
      locations: [],
      timeOfDay: [],
      favoritesOnly: false,
    });
  });

  it("dedupes and sorts multi-value filters, trimming blanks", async () => {
    const { normalizeEventFilters } = await loadState();
    const normalized = normalizeEventFilters({
      categories: [" Sport ", "Sport", "", null, "Career"],
      organizers: ["NU", "NU"],
    });
    expect(normalized.categories).toEqual(["Career", "Sport"]);
    expect(normalized.organizers).toEqual(["NU"]);
  });

  it("recovers to defaults when stored filters are corrupt json", async () => {
    const { loadEventFilters, defaultEventFilters } = await loadState();
    window.localStorage.setItem("events_miniapp_event_filters", "{not-json");
    expect(loadEventFilters()).toEqual(defaultEventFilters());
  });
});

describe("auth headers", () => {
  beforeEach(() => {
    window.Telegram = undefined;
  });

  it("omits the bearer token when there is no session", async () => {
    const { authHeaders, setSession } = await loadState();
    setSession("", null);
    const headers = authHeaders();
    expect(headers.Authorization).toBeUndefined();
    expect(headers["X-Language"]).toBeDefined();
    expect(headers["X-Theme"]).toBeDefined();
  });

  it("includes the telegram init data header only when present", async () => {
    const { authHeaders, setSession } = await loadState();
    setSession("tok", { id: 1 });
    expect(authHeaders()["X-Telegram-Init-Data"]).toBeUndefined();
    window.Telegram = { WebApp: { initData: "abc" } };
    expect(authHeaders()["X-Telegram-Init-Data"]).toBe("abc");
  });
});
