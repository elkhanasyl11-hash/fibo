import { lazy, Suspense } from "react"
import { Navigate, Route, Routes } from "react-router"

import { AppShell } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { getToken } from "@/lib/api"
import { Spinner } from "@/components/ui/spinner"
import { useSession } from "@/lib/session"
import { LoginPage } from "@/pages/login"
import { MachinesPage } from "@/pages/machines"
import { WelcomePage } from "@/pages/welcome"

const DashboardPage = lazy(() =>
  import("@/pages/dashboard").then((module) => ({
    default: module.DashboardPage,
  }))
)
const ChatPage = lazy(() =>
  import("@/pages/chat").then((x) => ({ default: x.ChatPage }))
)
const IncidentsPage = lazy(() =>
  import("@/pages/incidents").then((x) => ({ default: x.IncidentsPage }))
)
const InputPage = lazy(() =>
  import("@/pages/input").then((x) => ({ default: x.InputPage }))
)
const MachinePage = lazy(() =>
  import("@/pages/machine").then((x) => ({ default: x.MachinePage }))
)
const MachineFormPage = lazy(() =>
  import("@/pages/machine-form").then((x) => ({ default: x.MachineFormPage }))
)
const ManualsPage = lazy(() =>
  import("@/pages/manuals").then((x) => ({ default: x.ManualsPage }))
)
const ModelsPage = lazy(() =>
  import("@/pages/models").then((x) => ({ default: x.ModelsPage }))
)
const ReportsPage = lazy(() =>
  import("@/pages/reports").then((x) => ({ default: x.ReportsPage }))
)
const TelegramPage = lazy(() =>
  import("@/pages/telegram").then((x) => ({ default: x.TelegramPage }))
)
const OnboardingPage = lazy(() =>
  import("@/pages/onboarding").then((x) => ({ default: x.OnboardingPage }))
)

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { auth, loading, error, retry } = useSession()
  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (!auth && error && getToken())
    return (
      <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center gap-4 px-6">
        <h1 className="text-2xl font-medium">
          Не удалось связаться с сервером
        </h1>
        <p className="text-sm text-muted-foreground">
          Сессия сохранена. Повторите загрузку, когда сервер станет доступен.
        </p>
        <Button onClick={retry}>Повторить загрузку</Button>
      </main>
    )
  if (!auth) return <Navigate to="/login" replace />
  return children
}

function PublicOnly({ children }: { children: React.ReactNode }) {
  const { auth } = useSession()
  return auth ? <Navigate to="/app" replace /> : children
}

const pageFallback = (
  <div className="flex min-h-[40svh] items-center justify-center">
    <Spinner />
  </div>
)

export function App() {
  return (
    <Suspense fallback={pageFallback}>
      <Routes>
        <Route
          path="/"
          element={
            <PublicOnly>
              <WelcomePage />
            </PublicOnly>
          }
        />
        <Route path="/start" element={<OnboardingPage />} />
        <Route
          path="/login"
          element={
            <PublicOnly>
              <LoginPage />
            </PublicOnly>
          }
        />
        <Route
          path="/app"
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="machines" element={<MachinesPage />} />
          <Route path="machines/new" element={<MachineFormPage />} />
          <Route path="machines/:id" element={<MachinePage />} />
          <Route path="machines/:id/edit" element={<MachineFormPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="input" element={<InputPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route
            path="panel"
            element={<Navigate to="/app/input?tab=photo" replace />}
          />
          <Route path="manuals" element={<ManualsPage />} />
          <Route path="telegram" element={<TelegramPage />} />
          <Route path="models" element={<ModelsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

export default App
