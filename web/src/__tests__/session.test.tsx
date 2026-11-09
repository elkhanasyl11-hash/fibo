import { afterEach, expect, it, vi } from "vitest"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { SessionProvider, useSession } from "@/lib/session"
import { getToken, setToken } from "@/lib/api"
import type { AuthResponse } from "@/lib/types"

const auth = {
  token: "test-session",
  user: { id: 1, full_name: "Test owner" },
  workshop: { id: 1, name: "Test workshop" },
} as AuthResponse
function Probe() {
  const session = useSession()
  return (
    <>
      <span>
        {session.auth?.user.full_name ??
          (session.loading ? "loading" : "signed out")}
      </span>
      <button onClick={() => session.signIn(auth)}>sign in</button>
      <button onClick={session.signOut}>sign out</button>
      <button onClick={session.retry}>retry session</button>
      {session.error ? <span>session unavailable</span> : null}
    </>
  )
}
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <SessionProvider>
        <Probe />
      </SessionProvider>
    </QueryClientProvider>
  )
}
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  setToken(null)
})

it("updates the authenticated screen immediately and clears it on logout", async () => {
  setToken(null)
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(null, { status: 204 }))
  )
  mount()
  fireEvent.click(screen.getByText("sign in"))
  expect(await screen.findByText("Test owner")).toBeTruthy()
  expect(getToken()).toBe("test-session")
  fireEvent.click(screen.getByText("sign out"))
  expect(await screen.findByText("signed out")).toBeTruthy()
  expect(getToken()).toBeNull()
})

it("restores a stored session through the API after a reload", async () => {
  setToken("stored-session")
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(auth), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
  )
  vi.stubGlobal("fetch", fetchMock)
  mount()
  expect(await screen.findByText("Test owner")).toBeTruthy()
  await waitFor(() => expect(getToken()).toBe("test-session"))
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it("keeps sign-in and logout usable when browser storage rejects writes", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("storage blocked")
  })
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new Error("storage blocked")
  })
  setToken("memory-session")
  expect(getToken()).toBe("memory-session")
  setToken(null)
  expect(getToken()).toBeNull()
})

it("retains the session during a server outage and restores it on retry", async () => {
  setToken("stored-session")
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("offline"))
    .mockResolvedValue(new Response(JSON.stringify(auth), { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  mount()
  expect(await screen.findByText("session unavailable")).toBeTruthy()
  expect(getToken()).toBe("stored-session")
  fireEvent.click(screen.getByText("retry session"))
  expect(await screen.findByText("Test owner")).toBeTruthy()
})
