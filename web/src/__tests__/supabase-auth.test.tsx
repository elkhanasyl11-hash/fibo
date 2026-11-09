import { afterEach, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router"
import { I18nProvider } from "@/i18n"
import { LoginPage } from "@/pages/login"
import { AccountPage } from "@/pages/account"
import { OnboardingPage } from "@/pages/onboarding"
const auth = vi.hoisted(() => ({
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  getUser: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChange: vi.fn(() => ({
    data: { subscription: { unsubscribe: vi.fn() } },
  })),
}))
vi.mock("@/lib/supabase", () => ({
  supabaseAuth: true,
  supabase: { auth },
  authMessage: (e: Error) => e.message,
}))
vi.mock("@/components/toggles", () => ({ LangToggle: () => null, ThemeToggle: () => null }))
vi.mock("@/lib/session", () => ({
  useSession: () => ({ auth: null, loading: false, signIn: vi.fn() }),
}))
function mount(path = "/login") {
  localStorage.setItem("fibo.lang", "ru")
  render(
    <I18nProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/start" element={<OnboardingPage />} />
            <Route path="/account" element={<AccountPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>
  )
}
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  sessionStorage.clear()
  localStorage.clear()
})
it("opens a real Supabase profile after login", async () => {
  auth.signInWithPassword.mockResolvedValue({ error: null })
  auth.getUser.mockResolvedValue({
    data: {
      user: {
        id: "uuid",
        email: "owner@example.com",
        user_metadata: { full_name: "Владелец" },
      },
    },
    error: null,
  })
  mount()
  fireEvent.change(screen.getByLabelText("Почта"), {
    target: { value: "owner@example.com" },
  })
  fireEvent.change(screen.getByLabelText("Пароль"), {
    target: { value: "password42" },
  })
  fireEvent.submit(document.getElementById("login")!)
  expect(await screen.findByText("Мой профиль")).toBeTruthy()
  expect(auth.signInWithPassword).toHaveBeenCalledWith({
    email: "owner@example.com",
    password: "password42",
  })
})
it("shows failed login errors without opening a profile", async () => {
  auth.signInWithPassword.mockResolvedValue({
    error: { message: "Неверная почта или пароль." },
  })
  mount()
  fireEvent.submit(document.getElementById("login")!)
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "Неверная почта или пароль."
  )
  expect(auth.getUser).not.toHaveBeenCalled()
})
it("restores the verified user on a direct profile visit", async () => {
  auth.getUser.mockResolvedValue({
    data: {
      user: { id: "uuid", email: "saved@example.com", user_metadata: {} },
    },
    error: null,
  })
  mount("/account")
  expect(await screen.findByText("saved@example.com")).toBeTruthy()
})
it("saves signup metadata and requests confirmation when there is no session", async () => {
  sessionStorage.setItem(
    "fibo.onboarding",
    JSON.stringify({ profile: "bakery", step: 3 })
  )
  auth.signUp.mockResolvedValue({ data: { session: null }, error: null })
  auth.getUser.mockResolvedValue({
    data: { user: null },
    error: { name: "AuthSessionMissingError" },
  })
  mount("/start")
  for (const [id, value] of Object.entries({
    full_name: "Владелец",
    workshop_name: "Пекарня",
    email: "new@example.com",
    password: "password42",
  }))
    fireEvent.change(document.getElementById(id)!, { target: { value } })
  fireEvent.submit(document.getElementById("register-account")!)
  expect(await screen.findByText("Подтвердите почту")).toBeTruthy()
  expect(auth.signUp.mock.calls[0][0].options.data.workshop).toMatchObject({
    name: "Пекарня",
    profile: "bakery",
  })
  expect(localStorage.getItem("fibo.token")).toBeNull()
})
