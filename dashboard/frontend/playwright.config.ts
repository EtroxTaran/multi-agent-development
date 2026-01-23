import { defineConfig, devices } from "@playwright/test";

/**
 * Conductor Dashboard E2E Test Configuration
 *
 * Optimized for testing the multi-agent workflow dashboard.
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: "./e2e",

  /* Test execution settings */
  timeout: 30 * 1000, // 30s per test (workflow operations can be slow)
  expect: { timeout: 5 * 1000 }, // 5s for assertions
  fullyParallel: true,

  /* CI settings */
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,

  /* Reporters */
  reporter: [
    ["html", { outputFolder: "playwright-report" }],
    ["list"],
    ...(process.env.CI ? [["github" as const]] : []),
  ],

  /* Shared settings for all projects */
  use: {
    baseURL: "http://localhost:3000",

    /* Traces, screenshots, and videos for debugging */
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",

    /* Browser context options */
    viewport: { width: 1280, height: 720 },
    ignoreHTTPSErrors: true,
  },

  /* Output folder for test artifacts */
  outputDir: "test-results",

  /* Configure projects for major browsers */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],

  /* Run local dev server before starting tests */
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000, // 2 minutes for dev server to start
  },
});
