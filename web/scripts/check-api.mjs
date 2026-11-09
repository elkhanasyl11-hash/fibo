// Vercel hosts this directory as a static app; its Python API must live elsewhere.
const origin = process.env.VITE_API_URL?.trim().replace(/\/+$/, "")
if (!origin) {
  throw new Error(
    "Set VITE_API_URL to the public Fibo backend origin before deploying. A frontend-only deployment cannot register or sign in users."
  )
}
const url = new URL(origin)
if (
  url.protocol !== "https:" ||
  url.pathname !== "/" ||
  url.search ||
  url.hash ||
  url.username ||
  url.password
) {
  throw new Error(
    "VITE_API_URL must be an HTTPS origin, for example https://api.example.com (without /api/v1)."
  )
}
const response = await fetch(`${origin}/api/v1/health`, {
  signal: AbortSignal.timeout(15_000),
})
if (
  !response.ok ||
  !response.headers.get("content-type")?.includes("application/json")
) {
  throw new Error(
    `Fibo backend health check failed: HTTP ${response.status}. Check VITE_API_URL.`
  )
}
const health = await response.json()
if (health.status !== "ok" || health.database !== "ok") {
  throw new Error("Fibo backend or database is not ready. Deployment stopped.")
}
const frontendHost =
  process.env.VERCEL_ENV === "production"
    ? process.env.VERCEL_PROJECT_PRODUCTION_URL
    : process.env.VERCEL_URL
if (frontendHost) {
  const frontend = `https://${frontendHost}`
  const preflight = await fetch(`${origin}/api/v1/auth/register`, {
    method: "OPTIONS",
    headers: {
      Origin: frontend,
      "Access-Control-Request-Method": "POST",
      "Access-Control-Request-Headers": "content-type,authorization",
    },
    signal: AbortSignal.timeout(15_000),
  })
  const allowed = preflight.headers.get("access-control-allow-origin")
  if (!preflight.ok || (allowed !== frontend && allowed !== "*")) {
    throw new Error(
      `Backend CORS blocks ${frontend}. Add this origin to FIBO_CORS_ORIGINS before deploying.`
    )
  }
}
console.log("Fibo API and database are ready.")
