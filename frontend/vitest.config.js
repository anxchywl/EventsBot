import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "jsdom",
    environmentOptions: {
      jsdom: {
        url: "http://localhost:8000/",
      },
    },
    include: ["../tests/frontend/**/*.test.js"],
    setupFiles: [path.resolve(__dirname, "../tests/frontend/setup.js")],
    restoreMocks: true,
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname, "..")],
    },
  },
});
