import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router"

import "./index.css"
import { AppErrorBoundary } from "@/components/app-error-boundary"
import App from "./App.tsx"
import { ThemeProvider } from "@/components/theme-provider.tsx"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { I18nProvider } from "@/i18n"
import { ApiError } from "@/lib/api"
import { SessionProvider } from "@/lib/session"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (count, error) =>
        !(
          error instanceof ApiError &&
          error.status < 500 &&
          error.status > 0
        ) && count < 2,
    },
  },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="fibo.theme">
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <SessionProvider>
              <TooltipProvider delayDuration={200}>
                <AppErrorBoundary>
                  <App />
                </AppErrorBoundary>
                <Toaster position="top-center" />
              </TooltipProvider>
            </SessionProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  </StrictMode>
)
