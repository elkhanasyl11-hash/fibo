import { expect, test, type Page } from "@playwright/test"

const EMAIL = process.env.FIBO_E2E_EMAIL ?? ""
const PASSWORD = process.env.FIBO_E2E_PASSWORD ?? ""

test.skip(
  !EMAIL || !PASSWORD,
  "set FIBO_E2E_EMAIL and FIBO_E2E_PASSWORD (a workshop with at least one scored machine)"
)

async function signIn(page: Page, theme: "dark" | "light" = "dark") {
  await page.goto("/login")
  await page.evaluate(
    async ([email, password, mode]) => {
      localStorage.setItem("fibo.theme", mode)
      localStorage.setItem("fibo.lang", "ru")
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
      localStorage.setItem("fibo.token", (await response.json()).token)
    },
    [EMAIL, PASSWORD, theme]
  )
}

test("risk dashboard loads, a row expands and shows the risk factors", async ({
  page,
}) => {
  await signIn(page)
  await page.goto("/app")
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await expect(page.getByText("Что чинить первым")).toBeVisible()
  const expand = page
    .getByRole("button", { name: /Показать факторы риска|Факторы/ })
    .filter({ visible: true })
    .first()
  await expand.click()
  await expect(
    page.getByText(/Топ-3/).filter({ visible: true }).first()
  ).toBeVisible()
})

test("theme choice survives a reload", async ({ page }) => {
  await signIn(page, "dark")
  await page.goto("/app")
  await expect(page.locator("html")).toHaveClass(/dark/)
  await page.getByRole("button", { name: "Тема" }).click()
  await page.getByRole("menuitem", { name: "Светлая" }).click()
  await expect(page.locator("html")).toHaveClass(/light/)
  await page.reload()
  await expect(page.locator("html")).toHaveClass(/light/)
  await expect(page.locator("html")).not.toHaveClass(/dark/)
})

test("simulator recomputes the risk when a control changes", async ({
  page,
}) => {
  await signIn(page)
  await page.goto("/app/input?tab=simulator")
  await expect(page.getByText("Станет")).toBeVisible({ timeout: 15_000 })
  const responded = page.waitForResponse(
    (r) =>
      r.url().includes("/risk-scores/what-if") &&
      r.request().postData()?.includes('"maintenance_done":true') === true
  )
  await page.getByRole("button", { name: "Провести ТО" }).click()
  const response = await responded
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.scenario.risk_index).toBeLessThanOrEqual(body.current.risk_index)
})

for (const theme of ["dark", "light"] as const) {
  test(`screenshots (${theme})`, async ({ page }, info) => {
    test.skip(
      info.project.name === "tablet-1024",
      "screenshots: desktop and phone only"
    )
    await signIn(page, theme)
    const screens: [string, string][] = [
      ["risk", "/app"],
      ["incidents", "/app/incidents"],
      ["simulator", "/app/input?tab=simulator"],
      ["reports", "/app/reports"],
      ["assistant", "/app/chat"],
    ]
    for (const [name, path] of screens) {
      await page.goto(path)
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(1200)
      await page.screenshot({
        path: `../docs/screenshots/${name}-${theme}-${info.project.name}.png`,
      })
    }
  })
}
