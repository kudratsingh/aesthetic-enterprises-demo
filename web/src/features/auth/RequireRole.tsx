import { Navigate, Outlet } from 'react-router-dom'
import type { Role } from './session'
import { useAuth } from './useAuth'

/** Router-level role gate (CLAUDE.md §2.6). Convenience only — RLS is the
 * security boundary; a forged client sees empty datasets, not other tenants. */
export function RequireRole({ roles }: { roles: Role[] }) {
  const { claims } = useAuth()
  if (claims === null) return <Navigate to="/login" replace />
  if (!roles.includes(claims.role)) {
    return (
      <Navigate to={claims.role === 'hq_admin' ? '/hq' : '/operator'} replace />
    )
  }
  return <Outlet />
}
