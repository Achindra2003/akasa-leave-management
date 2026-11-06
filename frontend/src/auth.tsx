import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, type ReactNode } from 'react'
import { api, tokenStore, type User } from './api/client'

type AuthCtx = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/auth/me'),
    enabled: !!tokenStore.get(),
    retry: false,
  })

  // Drop every cached query except `me` - clearing `me` too would detach its observer and
  // the UI would never see the new user.
  const resetCache = useCallback(
    () => qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' }),
    [qc],
  )

  const logout = useCallback(() => {
    tokenStore.clear()
    resetCache()
    qc.setQueryData(['me'], null)
  }, [qc, resetCache])

  useEffect(() => {
    window.addEventListener('auth:expired', logout)
    return () => window.removeEventListener('auth:expired', logout)
  }, [logout])

  const login = async (email: string, password: string) => {
    const res = await api<{ accessToken: string; user: User }>('/auth/login', {
      body: { email, password },
    })
    tokenStore.set(res.accessToken)
    resetCache()
    qc.setQueryData(['me'], res.user)
    return res.user
  }

  const user = tokenStore.get() ? (me.data ?? null) : null
  return (
    <Ctx.Provider value={{ user, loading: !!tokenStore.get() && me.isLoading, login, logout }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAuth() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth outside AuthProvider')
  return c
}
