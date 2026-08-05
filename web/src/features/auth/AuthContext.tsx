import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../../api/client'
import { AuthCtx } from './context'
import type { AuthState } from './context'
import { clearToken, loadToken, parseClaims, storeToken } from './session'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => loadToken())

  const login = useCallback(async (email: string, password: string) => {
    const { data, error } = await api.POST('/api/v1/auth/login', {
      body: { email, password },
    })
    if (error !== undefined || data === undefined) {
      throw new Error('invalid email or password')
    }
    storeToken(data.access_token)
    setToken(data.access_token)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setToken(null)
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      token,
      claims: token === null ? null : parseClaims(token),
      login,
      logout,
    }),
    [token, login, logout],
  )

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}
