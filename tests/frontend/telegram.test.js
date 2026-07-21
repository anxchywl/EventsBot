import { describe, expect, it, vi } from "vitest";

async function loadTelegram() {
  vi.resetModules();
  return import("../../frontend/static/js/telegram.js?v=20260721-timeline-v7");
}

describe("frontend telegram helpers", () => {
  it("accepts supported event and invite start payloads", async () => {
    const { sanitizeStartPayload } = await loadTelegram();

    expect(sanitizeStartPayload(" event_123e4567-e89b-12d3-a456-426614174000 ")).toBe("event_123e4567-e89b-12d3-a456-426614174000");
    expect(sanitizeStartPayload(`invite_${"a".repeat(32)}`)).toBe(`invite_${"a".repeat(32)}`);
  });

  it("rejects unsafe start payloads", async () => {
    const { sanitizeStartPayload } = await loadTelegram();

    expect(sanitizeStartPayload("event_not-a-uuid")).toBe("");
    expect(sanitizeStartPayload("invite_short")).toBe("");
    expect(sanitizeStartPayload("javascript:alert(1)")).toBe("");
  });
});
