import { useState } from 'react'
import { fmtCents, fmtMonth, monthInputToPeriod } from '../../lib/format'
import type { RoyaltyRun } from './api'
import {
  locationMaps,
  useIssueInvoices,
  useLineItems,
  useLocations,
  useRunPeriod,
  useRuns,
} from './api'

export function HqRoyaltyRunsPage() {
  const [month, setMonth] = useState('2026-07')
  const [viewRun, setViewRun] = useState<string | null>(null)
  const locations = useLocations()
  const runs = useRuns()
  const runPeriod = useRunPeriod()
  const issue = useIssueInvoices()

  const { locName, orgName } = locationMaps(locations.data)
  const freshRun: RoyaltyRun | undefined = runPeriod.data
  const activeRunId = viewRun ?? freshRun?.id ?? null
  const pastItems = useLineItems(
    freshRun && activeRunId === freshRun.id ? null : activeRunId,
  )
  const items =
    freshRun && activeRunId === freshRun.id
      ? freshRun.line_items
      : (pastItems.data ?? [])
  const total = items.reduce((sum, li) => sum + li.amount_due_cents, 0)

  return (
    <>
      <h1>Royalty runs</h1>

      <section className="panel">
        <h2>Run a period</h2>
        <div className="row-form">
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button
            disabled={runPeriod.isPending}
            onClick={() => {
              setViewRun(null)
              runPeriod.mutate(monthInputToPeriod(month))
            }}
          >
            Run royalty period
          </button>
          {activeRunId !== null && (
            <button
              disabled={issue.isPending}
              onClick={() => issue.mutate(activeRunId)}
            >
              Issue invoices
            </button>
          )}
        </div>
        {runPeriod.isError && (
          <p className="bad">run failed (hq only; check the period)</p>
        )}
        {freshRun && (
          <p className={freshRun.reused ? 'hint' : 'good'}>
            {freshRun.reused
              ? `Inputs unchanged — returned existing v${freshRun.version} (idempotent).`
              : `Created v${freshRun.version} for ${fmtMonth(freshRun.period)}.`}
          </p>
        )}
        {issue.isSuccess && (
          <p className={issue.data.reused ? 'hint' : 'good'}>
            {issue.data.reused
              ? 'Invoices already existed for this run — returned as-is.'
              : `Issued ${issue.data.invoices.length} invoices (net-30).`}
          </p>
        )}
        {issue.isError && (
          <p className="bad">issuing failed (only the latest run version)</p>
        )}
      </section>

      <section>
        <h2>Runs</h2>
        <select
          value={activeRunId ?? ''}
          onChange={(e) => setViewRun(e.target.value)}
        >
          <option value="" disabled>
            select a run
          </option>
          {(runs.data ?? []).map((r) => (
            <option key={r.id} value={r.id}>
              {fmtMonth(r.period)} — v{r.version}
            </option>
          ))}
        </select>

        {activeRunId === null && (
          <p className="hint">
            Pick a run above, or run a period to see its line items.
          </p>
        )}
        <table className="tbl">
          <thead>
            <tr>
              <th>Org</th>
              <th>Location</th>
              <th className="num">Base</th>
              <th className="num">Rate</th>
              <th>Min applied</th>
              <th className="num">Amount due</th>
            </tr>
          </thead>
          <tbody>
            {items.map((li) => (
              <tr key={li.id}>
                <td>{orgName.get(li.org_id) ?? li.org_id.slice(0, 8)}</td>
                <td>
                  {locName.get(li.location_id) ?? li.location_id.slice(0, 8)}
                </td>
                <td className="num">{fmtCents(li.base_cents)}</td>
                <td className="num">{(Number(li.rate) * 100).toFixed(2)}%</td>
                <td>
                  {li.minimum_applied ? (
                    <span className="badge b-open">yes</span>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="num">{fmtCents(li.amount_due_cents)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={5}>Total due</td>
              <td className="num">
                <strong>{fmtCents(total)}</strong>
              </td>
            </tr>
          </tfoot>
        </table>

        {freshRun &&
          activeRunId === freshRun.id &&
          freshRun.exclusions.length > 0 && (
            <>
              <h2>Excluded locations</h2>
              <ul>
                {freshRun.exclusions.map((ex) => (
                  <li key={ex.location_id}>
                    {locName.get(ex.location_id) ?? ex.location_id.slice(0, 8)}{' '}
                    — <span className="hint">{ex.reason}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
      </section>
    </>
  )
}
