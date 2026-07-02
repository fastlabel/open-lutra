import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      pool: "threads",
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      exclude: ["src/api/generated/**"],
      coverage: {
        provider: "v8",
        // Exclude store pass-through setters; measure coverage on mutations / specialized algorithms that contain pure functions and logic.
        // Behavioral tests for stores in isolation are deferred to integration tests as a rule (see the testing policy in docs/DEVELOPMENT.md).
        include: [
          "src/lib/**",
          "src/features/**/mutations.ts",
          "src/features/**/quality-utils.tsx",
          "src/features/recording/store.ts",
          "src/stores/quality-history-store.ts",
          "src/stores/toast-store.ts",
        ],
        exclude: ["src/api/generated/**", "src/lib/utils.ts", "src/lib/query-client.ts"],
        thresholds: {
          "src/lib/**": { statements: 100, branches: 100, functions: 100 },
        },
      },
    },
  }),
);
