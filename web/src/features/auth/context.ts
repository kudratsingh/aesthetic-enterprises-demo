import { createContext } from 'react'
import type { Claims } from './session'

export interface AuthState {
  token: string | null
  claims: Claims | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthCtx = createContext<AuthState | null>(null)
