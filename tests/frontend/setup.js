import { beforeEach, vi } from "vitest";

function createStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(String(key)) ?? null,
    setItem: (key, value) => values.set(String(key), String(value)),
    removeItem: (key) => values.delete(String(key)),
    clear: () => values.clear(),
  };
}

beforeEach(() => {
  vi.unstubAllGlobals();
  const storage = createStorage();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: storage,
  });
  vi.stubGlobal("localStorage", storage);
  document.body.innerHTML = "";
  document.documentElement.lang = "";
  document.documentElement.removeAttribute("data-theme");
  window.Telegram = undefined;
});
