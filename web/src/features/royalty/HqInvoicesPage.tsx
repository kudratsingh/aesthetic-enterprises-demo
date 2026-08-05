import { fmtCents } from '../../lib/format'
import {
  locationMaps,
  useAging,
  useInvoices,
  useLocations,
  usePayInvoice,
} from './api'

export function HqInvoicesPage() {
  const invoices = useInvoices()
  const aging = useAging()
  const locations = useLocations()
  const pay = usePayInvoice()
  const { orgName } = locationMaps(locations.data)

  const live = (invoices.data ?? []).filter((inv) => inv.superseded_by === null)

  return (
    <>
      <h1>Invoices &amp; aging</h1>

      <section>
        <h2>Aging (unpaid, as of {aging.data?.as_of ?? '…'})</h2>
        <div className="stat-row">
          {(aging.data?.buckets ?? []).map((b) => (
            <div key={b.bucket} className="stat">
              <div className="stat-label">{b.bucket} days</div>
              <div className="stat-value">{fmtCents(b.amount_due_cents)}</div>
              <div className="hint">{b.invoice_count} invoices</div>
            </div>
          ))}
        </div>
        {aging.isSuccess &&
          aging.data.buckets.every((b) => b.invoice_count === 0) && (
            <p className="good">Nothing outstanding — every invoice is paid.</p>
          )}
      </section>

      <section>
        <h2>All invoices</h2>
        {invoices.isPending && <p className="hint">loading…</p>}
        {invoices.isSuccess && live.length === 0 && (
          <p className="hint">
            No invoices yet — run a royalty period and issue invoices from{' '}
            <strong>Royalty runs</strong>.
          </p>
        )}
        {live.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th>Org</th>
                <th className="num">Amount</th>
                <th>Issued</th>
                <th>Due</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {live.map((inv) => (
                <tr key={inv.id}>
                  <td>{orgName.get(inv.org_id) ?? inv.org_id.slice(0, 8)}</td>
                  <td className="num">{fmtCents(inv.amount_due_cents)}</td>
                  <td>{new Date(inv.issued_at).toLocaleDateString()}</td>
                  <td>{inv.due_date}</td>
                  <td>
                    <span className={`badge b-${inv.status}`}>
                      {inv.status}
                    </span>
                  </td>
                  <td>
                    {inv.status !== 'paid' && (
                      <button
                        disabled={pay.isPending}
                        onClick={() => pay.mutate(inv.id)}
                      >
                        Mark paid
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pay.isError && <p className="bad">payment recording failed</p>}
      </section>
    </>
  )
}
