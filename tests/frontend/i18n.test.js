import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadModules() {
  vi.resetModules();
  const stateModule = await import("../../frontend/static/js/state.js?v=20260721-timeline-v7");
  const i18nModule = await import("../../frontend/static/js/i18n.js?v=20260721-timeline-v7");
  return { ...stateModule, ...i18nModule };
}

describe("frontend i18n", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns localized labels with english fallback", async () => {
    const { setLang, t } = await loadModules();

    setLang("ru");

    expect(t("events")).toBe("События");
    expect(t("unknown_key")).toBe("unknown_key");
  });

  it("translates parameterized backend errors", async () => {
    const { setLang, translateError } = await loadModules();

    setLang("en");

    expect(translateError("Invalid verification code. Attempts remaining: 2.")).toBe("Invalid verification code. Attempts remaining: 2.");
    expect(translateError("Please wait 15 seconds before requesting a new code.")).toBe("Please wait 15 seconds before requesting a new code.");
    expect(translateError("Unknown backend error")).toBe("Unknown backend error");
  });

  it("formats category labels and reminder offsets", async () => {
    const { categoryLabel, formatReminderOffset, setLang } = await loadModules();

    setLang("en");

    expect(categoryLabel("computer science")).toBe("Computer Science");
    expect(categoryLabel("new-category")).toBe("New-Category");
    expect(formatReminderOffset(1500)).toBe("1d 1h");
    expect(formatReminderOffset(0)).toBe("0m");
  });
});
