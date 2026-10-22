import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

// The app's own Vite config (aliases, React plugin), plus a DOM. Component
// tests live beside the code as `*.test.tsx`; the Playwright smoke test is in
// `e2e/` and is not collected here (T-15).
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      include: ["src/**/*.test.{ts,tsx}"],
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
    },
  }),
);
