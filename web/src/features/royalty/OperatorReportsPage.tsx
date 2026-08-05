import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  dollarsToCents,
  fmtCents,
  fmtMonth,
  monthInputToPeriod,
} from '../../lib/format'
import {
  locationMaps,
  useCreateCorrection,
  useCreateReport,
  useLocations,
  useReports,
  useSubmitReport,
} from './api'

export function OperatorReportsPage() {
  const locations = useLocations()
  const reports = useReports()
  const create = useCreateReport()
  const submit = useSubmitReport()
  const correct = useCreateCorrection()

  const [locationId, setLocationId] = useState('')
  const [month, setMonth] = useState('2026-08')
  const [gross, setGross] = useState('')
  const [refunds, setRefunds] = useState('0')
  const [attested, setAttested] = useState(false)

  const { locName } = locationMaps(locations.data)

  const onCreate = (e: FormEvent) => {
    e.preventDefault()
    const grossCents = dollarsToCents(gross)
    const refundsCents = dollarsToCents(refunds)
    const loc = locationId !== '' ? locationId : (locations.data?.[0]?.id ?? '')
    if (grossCents === null || refundsCents === null || loc === '') return
    create.mutate({
      location_id: loc,
      period: monthInputToPeriod(month),
      gross_cents: grossCents,
      refunds_cents: refundsCents,
    })
  }

  const sorted = [...(reports.data ?? [])].sort((a, b) =>
    a.period === b.period
      ? (locName.get(a.location_id) ?? '').localeCompare(
          locName.get(b.location_id) ?? '',
        )
      : b.period.localeCompare(a.period),
  )

  return (
    <>
      <h1>Monthly reports</h1>
      <section className="panel">
        <h2>New report</h2>
        <form onSubmit={onCreate} className="row-form">
          <select
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
          >
            {(locations.data ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <input
            placeholder="gross $"
            inputMode="decimal"
            value={gross}
            onChange={(e) => setGross(e.target.value)}
          />
          <input
            placeholder="refunds $"
            inputMode="decimal"
            value={refunds}
            onChange={(e) => setRefunds(e.target.value)}
          />
          <button type="submit" disabled={create.isPending}>
            Create draft
          </button>
        </form>
        {create.isError && (
          <p className="bad">could not create draft (already reported?)</p>
        )}
      </section>

      <section>
        <h2>Reports</h2>
        <label className="hint">
          <input
            type="checkbox"
            checked={attested}
            onChange={(e) => setAttested(e.target.checked)}
          />{' '}
          I attest that submitted figures are accurate (required to submit —
          locks the report)
        </label>
        <table className="tbl">
          <thead>
            <tr>
              <th>Period</th>
              <th>Location</th>
              <th className="num">Gross</th>
              <th className="num">Refunds</th>
              <th className="num">Net base</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.id}>
                <td>{fmtMonth(r.period)}</td>
                <td>
                  {locName.get(r.location_id) ?? r.location_id.slice(0, 8)}
                </td>
                <td className="num">{fmtCents(r.gross_cents)}</td>
                <td className="num">{fmtCents(r.refunds_cents)}</td>
                <td className="num">{fmtCents(r.net_base_cents)}</td>
                <td>
                  <span className={`badge b-${r.status}`}>{r.status}</span>
                </td>
                <td>
                  {r.status === 'draft' && (
                    <button
                      disabled={!attested || submit.isPending}
                      title={attested ? '' : 'check the attestation box first'}
                      onClick={() => submit.mutate(r.id)}
                    >
                      Submit &amp; attest
                    </button>
                  )}
                  {r.status === 'locked' && (
                    <button
                      disabled={correct.isPending}
                      onClick={() => correct.mutate(r.id)}
                    >
                      Create correction
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {submit.isError && <p className="bad">submit failed</p>}
        {correct.isError && (
          <p className="bad">correction failed (one may already exist)</p>
        )}
      </section>
    </>
  )
}
