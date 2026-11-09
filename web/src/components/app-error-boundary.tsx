import { Component, type ReactNode } from "react"

export class AppErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center gap-4 px-6">
        <h1 className="text-2xl font-medium">Не удалось открыть экран</h1>
        <p className="text-sm text-muted-foreground">
          Обновите страницу. Сохранённые на сервере данные останутся доступны.
        </p>
        <button
          type="button"
          className="h-11 rounded-md bg-primary px-5 text-sm text-primary-foreground"
          onClick={() => window.location.reload()}
        >
          Обновить страницу
        </button>
        <a href="/app" className="text-center text-sm text-muted-foreground">
          Открыть дашборд
        </a>
      </main>
    )
  }
}
