import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadApi() {
  vi.resetModules();
  return import("../../frontend/static/js/api.js?v=20260628-security-v1");
}

describe("frontend api", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("sends json, language, theme, and session headers", async () => {
    const { request } = await loadApi();
    const { setLang, setSession, setTheme } = await import("../../frontend/static/js/state.js?v=20260628-security-v1");
    setLang("kk");
    setTheme("dark");
    setSession("abc123", { id: 1 });

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(request("/api/example", {
      method: "POST",
      body: JSON.stringify({ name: "Event" }),
      headers: { "X-Custom": "1" },
    })).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledWith("/api/example", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ name: "Event" }),
      headers: expect.objectContaining({
        "Content-Type": "application/json",
        Authorization: "Bearer abc123",
        "X-Language": "kk",
        "X-Theme": "dark",
        "X-Custom": "1",
      }),
    }));
  });

  it("throws backend error details for non-ok responses", async () => {
    const { request } = await loadApi();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: vi.fn().mockResolvedValue({ detail: "Too many requests" }),
    }));

    await expect(request("/api/rate-limited")).rejects.toMatchObject({
      message: "Too many requests",
      status: 429,
      payload: { detail: "Too many requests" },
    });
  });

  it("serializes event filters into query parameters", async () => {
    const { fetchEvents } = await loadApi();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue([]),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchEvents({
      sort: "time_desc",
      relevance: "all",
      categories: ["Career", "Sport"],
      organizers: ["NU"],
      locations: ["Main Hall"],
      favoritesOnly: true,
    });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/events?sort=time_desc&relevance=all&categories=Career%2CSport&organizers=NU&locations=Main+Hall&favorite_only=true");
  });
});
