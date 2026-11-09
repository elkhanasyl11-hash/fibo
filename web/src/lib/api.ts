// Session-authenticated API requests; the dev server forwards /api to the backend.

// Same origin by default; VITE_API_URL can point to another API origin.
const BASE = `${(import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "")}/api/v1`
const TOKEN_KEY = "fibo.token"
let memoryToken: string | null = null
let memoryOnly = false
const tokenListeners = new Set<() => void>()
export function subscribeToken(listener: () => void) {
  tokenListeners.add(listener)
  const onStorage = (event: StorageEvent) => {
    if (event.key === TOKEN_KEY) listener()
  }
  window.addEventListener("storage", onStorage)
  return () => {
    tokenListeners.delete(listener)
    window.removeEventListener("storage", onStorage)
  }
}

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {}
  ) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export function getToken(): string | null {
  if (memoryOnly) return memoryToken
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return memoryToken
  }
}

export function setToken(token: string | null): void {
  memoryToken = token
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
    memoryOnly = false
  } catch {
    memoryOnly = true
    // Private mode: retain the session in memory for this tab.
  }
  tokenListeners.forEach((listener) => listener())
}

async function parseError(response: Response): Promise<ApiError> {
  let body: {
    error?: {
      code?: string
      message?: string
      details?: Record<string, unknown>
    }
  } = {}
  try {
    body = await response.json()
  } catch {
    // not JSON (proxy error page)
  }
  const error = body.error ?? {}
  return new ApiError(
    response.status,
    error.code ?? "http_error",
    error.message ?? `HTTP ${response.status}`,
    error.details ?? {}
  )
}

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown; timeoutMs?: number } = {}
): Promise<T> {
  const { json, headers, timeoutMs = 20_000, ...rest } = init
  const timeout = AbortSignal.timeout(timeoutMs)
  const signal = rest.signal ? AbortSignal.any([rest.signal, timeout]) : timeout
  const token = getToken()
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...rest,
      signal,
      headers: {
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    })
  } catch {
    throw new ApiError(
      0,
      timeout.aborted ? "timeout" : "network",
      timeout.aborted ? "Request timed out" : "Server is unavailable"
    )
  }
  // Static hosts can return SPA HTML with status 200 when the API is missing.
  if (response.headers.get("content-type")?.includes("text/html")) {
    throw new ApiError(
      response.status,
      "api_unavailable",
      "Fibo API is not connected"
    )
  }
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(
      response.status,
      "invalid_response",
      "Invalid response from Fibo API"
    )
  }
}

export function query(
  params: Record<string, string | number | undefined | null>
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "")
      search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ""
}
