import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests",
  reporter: [
    ["junit", { outputFile: "results/junit.xml", embedAnnotationsAsProperties: true }],
    ["json", { outputFile: "results/results.json" }],
    ["html", { outputFolder: "results/html", open: "never" }],
  ],
  use: { browserName: "chromium" },
});
