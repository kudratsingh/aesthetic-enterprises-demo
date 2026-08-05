import { useState } from 'react'
import { fmtCents, fmtMonth, monthInputToPeriod } from '../../lib/format'
import { useComputeVariance, useResolveFlag, useVarianceFlags } from './api'

export function VariancePage() {
  const [month, setMonth] = useState('2026-07')
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const period = monthInputToPeriod(month)
  const flags = useVarianceFlags(period)
  const compute = useComputeVariance()
  const resolve = useResolveFlag()

  return (
    <>
      <h1>Variance reconciliation</h1>
      <p className="hint">
        Reported revenue vs the supply-implied floor: administrations × trailing
        avg net ticket. The floor can only say "implausibly low given product
        consumed" — that's the honest claim the data supports (R5).
      </p>

      <div className="row-form">
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
        <button
          disabled={compute.isPending}
          onClick={() => compute.mutate(period)}
        >
          Compute variance
        </button>
        {compute.isSuccess && (
          <span className="hint">
            threshold {compute.data.threshold} · avg ticket{' '}
            {fmtCents(compute.data.avg_net_ticket_cents)}
          </span>
        )}
        {compute.isError && (
          <span className="bad">compute failed (hq only)</span>
        )}
      </div>

      <table className="tbl">
        <thead>
          <tr>
            <th>Org</th>
            <th>Location</th>
            <th>Period</th>
            <th className="num">Reported net</th>
            <th className="num">Admins</th>
            <th className="num">× Avg ticket</th>
            <th className="num">= Floor</th>
            <th className="num">Ratio</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {(flags.data ?? []).map((f) => (
            <tr key={f.id}>
              <td>{f.org_name}</td>
              <td>{f.location_name}</td>
              <td>{fmtMonth(f.period)}</td>
              <td className="num">{fmtCents(f.reported_net_base_cents)}</td>
              <td className="num">{f.administrations}</td>
              <td className="num">{fmtCents(f.avg_net_ticket_cents)}</td>
              <td className="num">{fmtCents(f.expected_floor_cents)}</td>
              <td className="num">
                <span className="bad">{(f.ratio * 100).toFixed(0)}%</span>
              </td>
              <td>
                <span className={`badge b-${f.status}`}>{f.status}</span>
                {f.resolution_reason !== null && (
                  <div className="hint">{f.resolution_reason}</div>
                )}
              </td>
              <td>
                {resolvingId === f.id ? (
                  <div className="row-form">
                    <input
                      placeholder="resolution reason"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <button
                      disabled={resolve.isPending || reason.trim() === ''}
                      onClick={() => {
                        resolve.mutate({
                          flagId: f.id,
                          status: 'resolved',
                          reason,
                        })
                        setResolvingId(null)
                        setReason('')
                      }}
                    >
                      Confirm
                    </button>
                    <button onClick={() => setResolvingId(null)}>Cancel</button>
                  </div>
                ) : (
                  <div className="row-form">
                    {f.status === 'open' && (
                      <button
                        disabled={resolve.isPending}
                        onClick={() =>
                          resolve.mutate({
                            flagId: f.id,
                            status: 'reviewed',
                            reason: null,
                          })
                        }
                      >
                        Mark reviewed
                      </button>
                    )}
                    {f.status !== 'resolved' && (
                      <button onClick={() => setResolvingId(f.id)}>
                        Resolve…
                      </button>
                    )}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {flags.isSuccess && flags.data.length === 0 && (
        <p className="good">No open variance for {fmtMonth(period)}.</p>
      )}
    </>
  )
}
