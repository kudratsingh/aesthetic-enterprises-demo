import { useState } from 'react'
import { fmtCents, fmtMonth } from '../../lib/format'
import { useCollectInvoice } from '../collections/api'
import {
  locationMaps,
  useInvoices,
  useLineItems,
  useLocations,
  useRuns,
} from './api'

export function OperatorStatementsPage() {
  const runs = useRuns()
  const locations = useLocations()
  const invoices = useInvoices()
  const payNow = useCollectInvoice()
  const [selectedRun, setSelectedRun] = useState<string | null>(null)

  const runList = runs.data ?? []
  const activeRun = selectedRun ?? runList[0]?.id ?? null
  const lineItems = useLineItems(activeRun)
  const { locName } = locationMaps(locations.data)

  const total = (lineItems.data ?? []).reduce(
    (sum, li) => sum + li.amount_due_cents,
    0,
  )

  return (
    <>
      <h1>Statements &amp; invoices</h1>

      <section>
        <h2>Royalty statement</h2>
        {runList.length === 0 ? (
          <p className="hint">No royalty runs yet — HQ hasn't run a period.</p>
        ) : (
          <>
            <select
              value={activeRun ?? ''}
              onChange={(e) => setSelectedRun(e.target.value)}
            >
              {runList.map((r) => (
                <option key={r.id} value={r.id}>
                  {fmtMonth(r.period)} — v{r.version}
                </option>
              ))}
            </select>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Location</th>
                  <th className="num">Base</th>
                  <th className="num">Rate</th>
                  <th>Minimum applied</th>
                  <th className="num">Amount due</th>
                </tr>
              </thead>
              <tbody>
                {(lineItems.data ?? []).map((li) => (
                  <tr key={li.id}>
                    <td>
                      {locName.get(li.location_id) ??
                        li.location_id.slice(0, 8)}
                    </td>
                    <td className="num">{fmtCents(li.base_cents)}</td>
                    <td className="num">
                      {(Number(li.rate) * 100).toFixed(2)}%
                    </td>
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
                  <td colSpan={4}>Total</td>
                  <td className="num">
                    <strong>{fmtCents(total)}</strong>
                  </td>
                </tr>
              </tfoot>
            </table>
            <p className="hint">
              Everything billed is itemized here — transparency is the point
              (disputes are the expensive failure mode).
            </p>
          </>
        )}
      </section>

      <section>
        <h2>Invoices</h2>
        {invoices.isPending && <p className="hint">loading…</p>}
        {invoices.isSuccess &&
          invoices.data.filter((i) => i.superseded_by === null).length ===
            0 && (
            <p className="hint">
              No invoices yet — HQ hasn't issued this period.
            </p>
          )}
        <table className="tbl">
          <thead>
            <tr>
              <th>Issued</th>
              <th className="num">Amount</th>
              <th>Due</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(invoices.data ?? [])
              .filter((inv) => inv.superseded_by === null)
              .map((inv) => (
                <tr key={inv.id}>
                  <td>{new Date(inv.issued_at).toLocaleDateString()}</td>
                  <td className="num">{fmtCents(inv.amount_due_cents)}</td>
                  <td>{inv.due_date}</td>
                  <td>
                    <span className={`badge b-${inv.status}`}>
                      {inv.status}
                    </span>
                  </td>
                  <td>
                    {inv.status !== 'paid' && (
                      <button
                        disabled={payNow.isPending}
                        onClick={() => payNow.mutate(inv.id)}
                      >
                        Pay now (mock)
                      </button>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {payNow.isError && <p className="bad">mock payment failed</p>}
        <p className="hint">
          Pay now (mock) settles the invoice through the mock payment provider —
          checkout session, then a simulated provider callback.
        </p>
      </section>
    </>
  )
}
