import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests",
  reporter: [["junit", { outputFile: "results/junit.xml", embedAnnotationsAsProperties: true }]],
  use: { browserName: "chromium" },
});
