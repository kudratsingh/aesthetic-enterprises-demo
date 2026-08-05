// JWT session helpers. The token is the single piece of global client state
// (CLAUDE.md §2.6); claims are read client-side for routing only — the server
// re-verifies them on every request, RLS is the security boundary.

export type Role = 'hq_admin' | 'operator' | 'clinic_staff'

export interface Claims {
  sub: string
  org_id: string
  role: Role
  exp: number
}

const STORAGE_KEY = 'cnos.token'

export function parseClaims(token: string): Claims | null {
  const parts = token.split('.')
  const payload = parts[1]
  if (parts.length !== 3 || payload === undefined) return null
  try {
    const json: unknown = JSON.parse(
      atob(payload.replace(/-/g, '+').replace(/_/g, '/')),
    )
    if (typeof json !== 'object' || json === null) return null
    const c = json as Record<string, unknown>
    if (
      typeof c.sub !== 'string' ||
      typeof c.org_id !== 'string' ||
      typeof c.exp !== 'number' ||
      (c.role !== 'hq_admin' &&
        c.role !== 'operator' &&
        c.role !== 'clinic_staff')
    ) {
      return null
    }
    return { sub: c.sub, org_id: c.org_id, role: c.role, exp: c.exp }
  } catch {
    return null
  }
}

export function isExpired(claims: Claims, nowMs: number = Date.now()): boolean {
  return claims.exp * 1000 <= nowMs
}

export function loadToken(): string | null {
  const token = localStorage.getItem(STORAGE_KEY)
  if (token === null) return null
  const claims = parseClaims(token)
  if (claims === null || isExpired(claims)) {
    localStorage.removeItem(STORAGE_KEY)
    return null
  }
  return token
}

export function storeToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY)
}
