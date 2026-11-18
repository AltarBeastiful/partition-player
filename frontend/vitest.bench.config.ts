import { defineConfig } from "vitest/config";

// The benchmark runs (plan 0004): `npm run bench:form`. Not part of `npm test`.
export default defineConfig({
  test: { environment: "jsdom", include: ["src/**/*.bench.ts"], testTimeout: 600_000 },
});
