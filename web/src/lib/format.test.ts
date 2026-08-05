import { describe, expect, it } from 'vitest'
import {
  dollarsToCents,
  fmtCents,
  fmtMonth,
  monthInputToPeriod,
} from './format'

describe('fmtCents', () => {
  it('formats integer cents as USD', () => {
    expect(fmtCents(123456)).toBe('$1,234.56')
    expect(fmtCents(0)).toBe('$0.00')
  })
})

describe('fmtMonth', () => {
  it('labels a period date without timezone drift', () => {
    expect(fmtMonth('2026-07-01')).toBe('Jul 2026')
    expect(fmtMonth('2026-01-01')).toBe('Jan 2026')
  })
})

describe('monthInputToPeriod', () => {
  it('maps month input to first-of-month', () => {
    expect(monthInputToPeriod('2026-07')).toBe('2026-07-01')
  })
})

describe('dollarsToCents', () => {
  it('rounds to integer cents', () => {
    expect(dollarsToCents('1234.567')).toBe(123457)
    expect(dollarsToCents('0')).toBe(0)
  })
  it('rejects junk and negatives', () => {
    expect(dollarsToCents('')).toBeNull()
    expect(dollarsToCents('abc')).toBeNull()
    expect(dollarsToCents('-5')).toBeNull()
  })
})
