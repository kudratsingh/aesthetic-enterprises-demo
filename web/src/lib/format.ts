/** Money is integer cents end-to-end (PROJECT_CONTEXT §4); dollars exist only
 * at the presentation edge. */

export function fmtCents(cents: number): string {
  return (cents / 100).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
  })
}

/** '2026-07-01' → 'Jul 2026' (UTC-pinned so the label never shifts a month). */
export function fmtMonth(period: string): string {
  const [y, m] = period.split('-')
  if (y === undefined || m === undefined) return period
  return new Date(Date.UTC(Number(y), Number(m) - 1, 1)).toLocaleDateString(
    'en-US',
    {
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    },
  )
}

/** <input type="month"> value '2026-07' → API period '2026-07-01'. */
export function monthInputToPeriod(value: string): string {
  return `${value}-01`
}

/** Dollar string from a form input → integer cents; null when not a valid amount. */
export function dollarsToCents(value: string): number | null {
  if (value.trim() === '') return null
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0) return null
  return Math.round(n * 100)
}
