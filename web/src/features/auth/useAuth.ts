import { useContext } from 'react'
import { AuthCtx } from './context'
import type { AuthState } from './context'

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx)
  if (ctx === null) throw new Error('useAuth outside AuthProvider')
  return ctx
}

/** Authorization header for authenticated queries. */
export function useAuthHeaders(): Record<string, string> {
  const { token } = useAuth()
  return token === null ? {} : { Authorization: `Bearer ${token}` }
}
