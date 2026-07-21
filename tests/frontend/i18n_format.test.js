import { describe, expect, it, vi } from "vitest";

async function loadI18n() {
  vi.resetModules();
  const state = await import("../../frontend/static/js/state.js?v=20260721-timeline-v7");
  state.setLang("en");
  const i18n = await import("../../frontend/static/js/i18n.js?v=20260721-timeline-v7");
  return { ...i18n, ...state };
}

describe("formatReminderOffset", () => {
  it("breaks minutes into day/hour/minute parts", async () => {
    const { formatReminderOffset } = await loadI18n();
    expect(formatReminderOffset(30)).toBe("30m");
    expect(formatReminderOffset(60)).toBe("1h");
    expect(formatReminderOffset(90)).toBe("1h 30m");
    expect(formatReminderOffset(1440)).toBe("1d");
    expect(formatReminderOffset(1500)).toBe("1d 1h");
  });

  it("renders zero minutes explicitly", async () => {
    const { formatReminderOffset } = await loadI18n();
    expect(formatReminderOffset(0)).toBe("0m");
  });
});

describe("formatEventDate", () => {
  it("falls back to raw fields for an unparseable date", async () => {
    const { formatEventDate } = await loadI18n();
    expect(formatEventDate({ date: "not-a-date", time: "10:00" })).toBe("not-a-date 10:00");
  });

  it("produces a formatted string for a valid date", async () => {
    const { formatEventDate } = await loadI18n();
    const out = formatEventDate({ date: "2026-05-01", time: "18:30" });
    expect(typeof out).toBe("string");
    expect(out).not.toBe("2026-05-01 18:30");
  });
});

describe("translateError", () => {
  it("returns empty string for falsy input", async () => {
    const { translateError } = await loadI18n();
    expect(translateError("")).toBe("");
    expect(translateError(null)).toBe("");
  });

  it("passes through messages it does not recognize", async () => {
    const { translateError } = await loadI18n();
    expect(translateError("Some brand new error")).toBe("Some brand new error");
  });

  it("fills the remaining-attempts template from the backend message", async () => {
    const { translateError } = await loadI18n();
    const out = translateError("Invalid verification code. Attempts remaining: 3.");
    expect(out).toContain("3");
  });

  it("fills the resend-wait template from the backend message", async () => {
    const { translateError } = await loadI18n();
    const out = translateError("Please wait 42 seconds before requesting a new code.");
    expect(out).toContain("42");
  });
});

describe("categoryLabel", () => {
  it("title-cases an unknown category name", async () => {
    const { categoryLabel } = await loadI18n();
    expect(categoryLabel("robotics club")).toBe("Robotics Club");
  });

  it("handles empty input safely", async () => {
    const { categoryLabel } = await loadI18n();
    expect(categoryLabel("")).toBe("");
    expect(categoryLabel(null)).toBe("");
  });
});
