# Fibo web dashboard

Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui, TanStack Query, react-router, motion, Recharts.
Dark theme by default (Light / Dark / System in the top bar), Russian and Kazakh.

## Run

```bash
npm install
npm run dev          # http://localhost:5173, the backend must run on :8000
```

The dev server proxies `/api` to the backend and adds `X-Fibo-Api-Key` from the repository `.env`
(`FIBO_DASHBOARD_API_KEY`, empty = disabled in dev). Another backend: `FIBO_WEB_API_TARGET=http://host:8000`.

```bash
npm run build        # type check + production bundle in dist/
npm test             # Vitest unit tests
npm run test:e2e     # Playwright (uses the installed Google Chrome), dev server and backend running
npm run lint
```

## Docker

`docker compose --profile web up` builds this folder and serves it on http://localhost:8080 with nginx;
`/api` goes to the `backend` service (same origin, no CORS).

## Structure

```
src/
  api/mocks/        adapters for features the backend does not have yet (TODO backend)
  components/       shell, shared blocks (risk bar, KPI, player, dialogs), ui/ = shadcn
  i18n/             ru.ts, kk.ts, features.ts (model feature names)
  lib/              api client, queries, stats, format, motion tokens, session
  pages/            dashboard (Risk), machine (tabs), input (simulator), incidents, chat, reports, ...
  __tests__/        unit tests
e2e/                Playwright scenarios
```

Screen to endpoint table and what is not on the backend: `../docs/frontend-inventory.md`.
Decisions: `../docs/frontend-decisions.md`.
