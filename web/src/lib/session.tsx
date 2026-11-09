import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react"

import { api, ApiError, getToken, setToken, subscribeToken } from "./api"
import type { AuthResponse } from "./types"

interface Session {
  auth: AuthResponse | null
  loading: boolean
  error: unknown
  retry: () => void
  signIn: (auth: AuthResponse) => void
  signOut: () => void
}

const SessionContext = createContext<Session | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const token = useSyncExternalStore(subscribeToken, getToken, () => null)
  const me = useQuery({
    queryKey: ["me"],
    enabled: token !== null,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: async () => {
      try {
        const auth = await api<AuthResponse>("/auth/me")
        setToken(auth.token)
        return auth
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) setToken(null)
        throw error
      }
    },
  })
  const signIn = useCallback(
    (auth: AuthResponse) => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== "me" })
      client.setQueryData(["me"], auth)
      setToken(auth.token)
    },
    [client]
  )
  const signOut = useCallback(() => {
    void api("/auth/logout", { method: "POST" }).catch(() => {})
    setToken(null)
    client.clear()
  }, [client])
  const refetchSession = me.refetch
  const retry = useCallback(() => {
    void refetchSession()
  }, [refetchSession])
  const value = useMemo(
    () => ({
      auth: token ? (me.data ?? null) : null,
      loading: token !== null && me.isPending,
      error: me.error,
      retry,
      signIn,
      signOut,
    }),
    [token, me.data, me.isPending, me.error, retry, signIn, signOut]
  )
  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  )
}

export function useSession(): Session {
  const context = useContext(SessionContext)
  if (!context) throw new Error("useSession outside SessionProvider")
  return context
}
