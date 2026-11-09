import { act, render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ThemeProvider, useTheme } from "@/components/theme-provider"

function Switch() {
  const { setTheme } = useTheme()
  return <button onClick={() => setTheme("light")}>go</button>
}

describe("theme", () => {
  it("defaults to dark and persists the choice", () => {
    if (!window.matchMedia) {
      window.matchMedia = (() => ({
        matches: false,
        addEventListener() {},
        removeEventListener() {},
      })) as unknown as typeof window.matchMedia
    }
    localStorage.removeItem("fibo.theme")
    const view = render(
      <ThemeProvider defaultTheme="dark" storageKey="fibo.theme">
        <Switch />
      </ThemeProvider>
    )
    expect(document.documentElement.classList.contains("dark")).toBe(true)
    act(() => view.getByText("go").click())
    expect(localStorage.getItem("fibo.theme")).toBe("light")
    expect(document.documentElement.classList.contains("light")).toBe(true)
  })
})
