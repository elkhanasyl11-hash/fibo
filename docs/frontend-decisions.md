# Frontend decisions (redesign, 9 Nov 2026)

F1. Stack kept (Vite + React + TS + Tailwind v4 + shadcn). Built on the existing screens, nothing rewritten from scratch.
F2. API base stays the Vite proxy `/api` (no CORS, the dashboard key stays server-side). `VITE_API_URL` overrides it
    for a separately hosted backend.
F3. Palette from the Fibo logo: navy surfaces, blue primary (#4A9EFF dark / #2563EB light), orange #FF6B0D only for
    critical states and the single main action. Dark is the default theme; Light / Dark / System are stored in
    localStorage, an inline script in index.html applies the class before the first paint (no flash).
F4. Inter is self-hosted through @fontsource (no Google Fonts CDN).
F5. The workshop profile comes from the workshop itself (set at sign-up, it decides the risk model and equipment
    catalog), so the header shows it as the workshop's badge instead of a free switch that would show wrong data.
F6. "Назначить ТО" has no backend endpoint: the plan is stored in the browser (clearly labelled); marking maintenance
    done is real (`last_maintenance_at`).
F7. No SSE on the backend: polling (15 s lists, 2 s for an incident being analysed).
F8. Risk priority in tenge is never recomputed on the client; only displayed. The what-if simulator calls the backend.
