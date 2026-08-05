import { fmtCents } from '../../lib/format'
import { locationMaps, useAging, useInvoices, useLocations } from './api'

export function HqInvoicesPage() {
  const invoices = useInvoices()
  const aging = useAging()
  const locations = useLocations()
  const { orgName } = locationMaps(locations.data)

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
      </section>

      <section>
        <h2>All invoices</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>Org</th>
              <th className="num">Amount</th>
              <th>Issued</th>
              <th>Due</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(invoices.data ?? [])
              .filter((inv) => inv.superseded_by === null)
              .map((inv) => (
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
                </tr>
              ))}
          </tbody>
        </table>
      </section>
    </>
  )
}
