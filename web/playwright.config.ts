import { defineConfig } from "@playwright/test"

// Runs against the running dev server (npm run dev) and backend. Uses the installed Google Chrome,
// so no browser download is needed. Sign-in comes from FIBO_E2E_EMAIL / FIBO_E2E_PASSWORD.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.FIBO_E2E_URL ?? "http://localhost:5173",
    channel: "chrome",
    locale: "ru-RU",
  },
  projects: [
    { name: "desktop-1440", use: { viewport: { width: 1440, height: 900 } } },
    { name: "tablet-1024", use: { viewport: { width: 1024, height: 768 } } },
    {
      name: "phone-390",
      use: {
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
})
