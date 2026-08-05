import { useState } from 'react'
import { fmtCents, fmtMonth, monthInputToPeriod } from '../../lib/format'
import { useLocationKpis, useNetworkKpis } from './api'

export function DashboardPage() {
  const [month, setMonth] = useState('2026-07')
  const period = monthInputToPeriod(month)
  const network = useNetworkKpis(6)
  const locations = useLocationKpis(period)

  const latest =
    network.data?.find((r) => r.period === period) ?? network.data?.[0]

  return (
    <>
      <h1>Network dashboard</h1>
      <div className="row-form">
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
      </div>

      {network.isPending && <p className="hint">loading network KPIs…</p>}
      {latest && (
        <div className="stat-row">
          <div className="stat">
            <div className="stat-label">Leads</div>
            <div className="stat-value">{latest.leads}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Consults</div>
            <div className="stat-value">{latest.consults}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Sales</div>
            <div className="stat-value">{latest.sales}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Treatments</div>
            <div className="stat-value">{latest.treatments_completed}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Reported net base</div>
            <div className="stat-value">
              {fmtCents(latest.reported_net_base_cents)}
            </div>
          </div>
        </div>
      )}

      <section>
        <h2>Trend (6 months)</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>Period</th>
              <th className="num">Leads</th>
              <th className="num">Consults</th>
              <th className="num">Sales</th>
              <th className="num">Treatments</th>
              <th className="num">Plan value</th>
              <th className="num">Reported net</th>
            </tr>
          </thead>
          <tbody>
            {(network.data ?? []).map((r) => (
              <tr key={r.period}>
                <td>{fmtMonth(r.period)}</td>
                <td className="num">{r.leads}</td>
                <td className="num">{r.consults}</td>
                <td className="num">{r.sales}</td>
                <td className="num">{r.treatments_completed}</td>
                <td className="num">{fmtCents(r.plan_value_cents)}</td>
                <td className="num">{fmtCents(r.reported_net_base_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Locations vs ramp target — {fmtMonth(period)}</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>Org</th>
              <th>Location</th>
              <th className="num">Months active</th>
              <th className="num">Treatments</th>
              <th className="num">Target</th>
              <th className="num">Attainment</th>
              <th className="num">Reported net</th>
            </tr>
          </thead>
          <tbody>
            {(locations.data ?? []).map((r) => (
              <tr key={r.location_id}>
                <td>{r.org_name}</td>
                <td>{r.location_name}</td>
                <td className="num">{r.months_active}</td>
                <td className="num">{r.treatments_completed}</td>
                <td className="num">{r.target_treatments}</td>
                <td className="num">
                  <span
                    className={
                      r.attainment >= 1
                        ? 'good'
                        : r.attainment >= 0.7
                          ? ''
                          : 'bad'
                    }
                  >
                    {(r.attainment * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="num">{fmtCents(r.reported_net_base_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  )
}
