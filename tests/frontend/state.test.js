import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadState() {
  vi.resetModules();
  return import("../../frontend/static/js/state.js?v=20260628-security-v1");
}

describe("frontend state", () => {
  beforeEach(() => {
    Object.defineProperty(window, "scrollY", {
      configurable: true,
      value: 120,
    });
  });

  it("normalizes persisted event filters", async () => {
    const { normalizeEventFilters } = await loadState();

    expect(normalizeEventFilters({
      sort: "participants_desc",
      relevance: "all",
      categories: [" Sport ", "sport", "", null],
      organizers: ["NU", "NU", "  Club"],
      locations: "not-an-array",
      timeOfDay: ["evening"],
      favoritesOnly: 1,
    })).toEqual({
      sort: "participants_desc",
      relevance: "all",
      categories: ["Sport", "sport"],
      organizers: ["Club", "NU"],
      locations: [],
      timeOfDay: ["evening"],
      favoritesOnly: true,
    });
  });

  it("persists language, theme, filters, and auth headers", async () => {
    const {
      authHeaders,
      setEventFilters,
      setLang,
      setSession,
      setTheme,
      state,
    } = await loadState();

    window.Telegram = { WebApp: { initData: "telegram-init-data" } };
    setLang("ru-RU");
    setTheme("dark");
    setSession("session-token", { id: 1 });
    const filters = setEventFilters({ categories: ["career", "career"], favoritesOnly: true });

    expect(state.lang).toBe("ru");
    expect(document.documentElement.lang).toBe("ru");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(filters.categories).toEqual(["career"]);
    expect(JSON.parse(window.localStorage.getItem("events_miniapp_event_filters"))).toEqual(filters);
    expect(authHeaders()).toMatchObject({
      Authorization: "Bearer session-token",
      "X-Telegram-Init-Data": "telegram-init-data",
      "X-Language": "ru",
      "X-Theme": "dark",
    });
  });
});
