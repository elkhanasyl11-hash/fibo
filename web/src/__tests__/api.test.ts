import { afterEach, describe, expect, it, vi } from "vitest"

import { api, ApiError, query } from "@/lib/api"

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status: number) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status }))
}

describe("api wrapper", () => {
  it("unwraps the backend error envelope", async () => {
    const envelope = {
      error: {
        code: "validation_failed",
        message: "bad",
        details: { field: "x" },
      },
    }
    vi.stubGlobal("fetch", respond(envelope, 422))
    const error = await api("/x").catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 422,
      code: "validation_failed",
      message: "bad",
      details: { field: "x" },
    })
  })

  it("reports a network failure as status 0", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("offline")
      })
    )
    await expect(api("/x")).rejects.toMatchObject({
      status: 0,
      code: "network",
    })
  })

  it("rejects a static-host HTML fallback instead of treating it as a sign-in response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("<!doctype html><html></html>", {
            status: 200,
            headers: { "Content-Type": "text/html; charset=utf-8" },
          })
      )
    )
    await expect(
      api("/auth/login", { method: "POST", json: {} })
    ).rejects.toMatchObject({
      code: "api_unavailable",
    })
  })

  it("reports malformed JSON as an API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("broken", { status: 200 }))
    )
    await expect(
      api("/auth/register", { method: "POST", json: {} })
    ).rejects.toMatchObject({
      code: "invalid_response",
    })
  })

  it("sends JSON and the sign-in token", async () => {
    localStorage.setItem("fibo.token", "abc")
    const fetchMock = respond({ ok: true }, 200)
    vi.stubGlobal("fetch", fetchMock)
    await api("/y", { method: "POST", json: { a: 1 } })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ]
    expect(url).toBe("/api/v1/y")
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
      Authorization: "Bearer abc",
    })
    expect(init.body).toBe('{"a":1}')
  })

  it("builds query strings without empty values", () => {
    expect(query({ a: 1, b: "", c: null, d: undefined, e: "x y" })).toBe(
      "?a=1&e=x+y"
    )
  })
})
