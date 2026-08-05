import { describe, expect, it } from 'vitest'
import { isExpired, parseClaims } from './session'

function fakeToken(payload: object): string {
  const b64 = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${b64}.signature`
}

const VALID = {
  sub: 'user-1',
  org_id: 'org-1',
  role: 'operator',
  exp: 4102444800, // 2100-01-01
}

describe('parseClaims', () => {
  it('parses a well-formed token', () => {
    expect(parseClaims(fakeToken(VALID))).toEqual(VALID)
  })

  it('rejects malformed tokens', () => {
    expect(parseClaims('not-a-jwt')).toBeNull()
    expect(parseClaims('a.b')).toBeNull()
    expect(parseClaims('a.%%%.c')).toBeNull()
  })

  it('rejects unknown roles and missing claims', () => {
    expect(parseClaims(fakeToken({ ...VALID, role: 'superuser' }))).toBeNull()
    expect(parseClaims(fakeToken({ role: 'operator' }))).toBeNull()
  })
})

describe('isExpired', () => {
  it('is false before exp and true after', () => {
    const claims = parseClaims(fakeToken(VALID))
    expect(claims).not.toBeNull()
    if (claims === null) return
    expect(isExpired(claims, Date.UTC(2099, 0, 1))).toBe(false)
    expect(isExpired(claims, Date.UTC(2101, 0, 1))).toBe(true)
  })
})
