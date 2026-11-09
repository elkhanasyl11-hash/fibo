# Frontend inventory (before the redesign, 9 Nov 2026)

Stack: Vite 8 + React 19 + TypeScript (strict) + Tailwind v4 + shadcn/ui (radix-nova) + TanStack Query 5 +
react-router 8 + motion + Recharts 3 + lucide. Node 24. API through the Vite dev proxy `/api -> :8000`
(the proxy adds `X-Fibo-Api-Key`, the key never reaches the bundle). No mocks: every screen calls the real backend.

## Routes (baseline)

| Route | Screen | State |
| --- | --- | --- |
| `/` | Landing | works |
| `/start` | 5-step onboarding survey + sign-up | works (AI questions live) |
| `/login` | Sign-in | works |
| `/app` | Overview: KPIs with deltas, workshop loss chart, Fibo recommends, priority table, 7-day movers, causes, event feed, heat map | works, refreshes every 15 s |
| `/app/machines`, `/new`, `/:id`, `/:id/edit` | Machines list, form, machine page (risk, what-if, AI advice, SHAP, coverage, history, sound, incidents) | works |
| `/app/chat` | AI assistant | works |
| `/app/panel` | Panel photo -> confirm readings | works |
| `/app/manuals` | PDF manuals + indexing status | works |
| `/app/telegram` | Bot hand-off, owner alerts link, team | works |
| `/app/models` | Model metrics (real numbers only) | works |

## Screen -> endpoints

| Screen | Endpoints | Status |
| --- | --- | --- |
| Auth / onboarding | `POST /auth/register`, `/auth/login`, `GET /auth/me`, `PUT /auth/survey`, `POST /onboarding/questions`, `POST /auth/telegram-link` | connected |
| Risk dashboard | `GET /risk-scores/ranking`, `/machines?workshop_id`, `/incidents`, `/reports/summary`, `/machines/{id}/risk-history?daily=true`, `POST /risk-scores/recompute`, `POST /ai/advice` | connected |
| Machine | `GET /machines/{id}/summary`, `/machines/{id}/readings`, `/incidents?machine_id`, `/incidents/{id}`, `/machines/{id}/manuals`, `/media/{path}`, `POST /risk-scores/what-if`, `PATCH /machines/{id}`, `DELETE /machines/{id}` | connected |
| Input & simulator | `POST /readings`, `POST /readings/panel-photo`, `POST /risk-scores/what-if` | connected |
| Incidents | `GET /incidents`, `GET /incidents/{id}`, `PATCH /incidents/{id}/resolve`, `POST /incidents/{id}/retry`, `GET /incidents/{id}/manual-excerpts`, `/media/{path}` (audio) | connected |
| Assistant | `POST /ai/assistant/chat` | connected |
| Reports | `GET /reports/summary`, `GET /reports/export.csv` | connected |
| Manuals | `POST /machines/{id}/manuals`, `GET /machines/{id}/manuals` | connected |

## Not on the backend (adapter with a clear label, `src/api/mocks/`)

| Feature | Why | Frontend behaviour |
| --- | --- | --- |
| "Назначить ТО" (planned date, assignee, comment) | no maintenance-plan table/endpoint | plan kept in this browser (`localStorage`), labelled; "ТО выполнено" uses the real `PATCH /machines/{id}` (`last_maintenance_at`) |
| Server-sent events | no SSE endpoint | polling: lists every 15 s, a processing incident every 2 s |
| Report history (list of generated PDFs) | backend builds the report on request | period picker + live summary + CSV download |
