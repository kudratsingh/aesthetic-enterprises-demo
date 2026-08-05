import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../auth/useAuth'
import { locationMaps, useLocations } from '../royalty/api'
import {
  useAdminister,
  useLots,
  useOnHand,
  useProducts,
  useReceiveLot,
  useRecall,
  useShip,
} from './api'

export function SupplyPage() {
  const { claims } = useAuth()
  const isHq = claims?.role === 'hq_admin'
  const products = useProducts()
  const lots = useLots()
  const onHand = useOnHand()
  const locations = useLocations()
  const receive = useReceiveLot()
  const ship = useShip()
  const administer = useAdminister()

  const [recallLot, setRecallLot] = useState<string | null>(null)
  const recall = useRecall(recallLot)

  const [lotCode, setLotCode] = useState('')
  const [productId, setProductId] = useState('')
  const [shipLot, setShipLot] = useState('')
  const [shipLoc, setShipLoc] = useState('')
  const [shipQty, setShipQty] = useState('10')
  const [admLot, setAdmLot] = useState('')
  const [admLoc, setAdmLoc] = useState('')
  const [patientRef, setPatientRef] = useState('')

  const { locName } = locationMaps(locations.data)

  const onReceive = (e: FormEvent) => {
    e.preventDefault()
    const pid = productId !== '' ? productId : (products.data?.[0]?.id ?? '')
    if (pid === '' || lotCode.trim() === '') return
    receive.mutate({
      product_id: pid,
      lot_code: lotCode.trim(),
      supplier: 'Demo Supplier',
      expiry: '2027-12-01',
    })
    setLotCode('')
  }

  const onShip = (e: FormEvent) => {
    e.preventDefault()
    const lot = shipLot !== '' ? shipLot : (lots.data?.[0]?.id ?? '')
    const loc = shipLoc !== '' ? shipLoc : (locations.data?.[0]?.id ?? '')
    const qty = Number(shipQty)
    if (lot === '' || loc === '' || !Number.isInteger(qty) || qty <= 0) return
    ship.mutate({ lot_id: lot, location_id: loc, qty })
  }

  const onAdminister = (e: FormEvent) => {
    e.preventDefault()
    const lot = admLot !== '' ? admLot : (lots.data?.[0]?.id ?? '')
    const loc = admLoc !== '' ? admLoc : (locations.data?.[0]?.id ?? '')
    if (lot === '' || loc === '' || patientRef.trim() === '') return
    administer.mutate({
      lot_id: lot,
      location_id: loc,
      synthetic_patient_ref: patientRef.trim(),
      qty: 1,
    })
  }

  return (
    <>
      <h1>Supply &amp; traceability</h1>

      {isHq && (
        <section className="panel">
          <h2>Receive lot (HQ)</h2>
          <form onSubmit={onReceive} className="row-form">
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
            >
              {(products.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <input
              placeholder="lot code"
              value={lotCode}
              onChange={(e) => setLotCode(e.target.value)}
            />
            <button type="submit" disabled={receive.isPending}>
              Receive
            </button>
          </form>

          <h2>Ship to location (HQ)</h2>
          <form onSubmit={onShip} className="row-form">
            <select
              value={shipLot}
              onChange={(e) => setShipLot(e.target.value)}
            >
              {(lots.data ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.lot_code} — {l.product_name}
                </option>
              ))}
            </select>
            <select
              value={shipLoc}
              onChange={(e) => setShipLoc(e.target.value)}
            >
              {(locations.data ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
            <input
              inputMode="numeric"
              value={shipQty}
              onChange={(e) => setShipQty(e.target.value)}
            />
            <button type="submit" disabled={ship.isPending}>
              Ship
            </button>
            {ship.isSuccess && <span className="good">shipped</span>}
          </form>
        </section>
      )}

      {!isHq && (
        <section className="panel">
          <h2>Record administration</h2>
          <form onSubmit={onAdminister} className="row-form">
            <select value={admLot} onChange={(e) => setAdmLot(e.target.value)}>
              {(lots.data ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.lot_code} — {l.product_name}
                </option>
              ))}
            </select>
            <select value={admLoc} onChange={(e) => setAdmLoc(e.target.value)}>
              {(locations.data ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
            <input
              placeholder="synthetic patient ref"
              value={patientRef}
              onChange={(e) => setPatientRef(e.target.value)}
            />
            <button type="submit" disabled={administer.isPending}>
              Record
            </button>
            {administer.isSuccess && <span className="good">recorded</span>}
            {administer.isError && (
              <span className="bad">
                {administer.error.message === 'expired_lot'
                  ? 'lot is expired — cannot administer (R6)'
                  : administer.error.message === 'insufficient_stock'
                    ? 'insufficient on-hand for that lot at this location'
                    : 'recording failed'}
              </span>
            )}
          </form>
          <p className="hint">
            Synthetic references only — this system never stores PHI.
          </p>
        </section>
      )}

      <section>
        <h2>On hand</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>Location</th>
              <th>Lot</th>
              <th>Product</th>
              <th>Expiry</th>
              <th className="num">On hand</th>
            </tr>
          </thead>
          <tbody>
            {(onHand.data ?? []).map((r) => (
              <tr key={`${r.location_id}-${r.lot_id}`}>
                <td>{r.location_name}</td>
                <td>{r.lot_code}</td>
                <td>{r.product_name}</td>
                <td>{r.expiry}</td>
                <td className="num">{r.on_hand}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Recall query</h2>
        <div className="row-form">
          <select
            value={recallLot ?? ''}
            onChange={(e) => setRecallLot(e.target.value)}
          >
            <option value="" disabled>
              select a lot
            </option>
            {(lots.data ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.lot_code} — {l.product_name}
              </option>
            ))}
          </select>
        </div>
        {recall.isSuccess && (
          <>
            <p>
              <strong>{recall.data.lot_code}</strong> (
              {recall.data.product_name}, {recall.data.supplier}, expires{' '}
              {recall.data.expiry}):{' '}
              <strong>{recall.data.total_administrations}</strong>{' '}
              administrations affected.
            </p>
            <table className="tbl">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Location</th>
                  <th>Org</th>
                  <th>Patient ref (synthetic)</th>
                  <th className="num">Qty</th>
                </tr>
              </thead>
              <tbody>
                {recall.data.rows.map((r) => (
                  <tr key={r.administration_id}>
                    <td>{new Date(r.administered_at).toLocaleDateString()}</td>
                    <td>{locName.get(r.location_name) ?? r.location_name}</td>
                    <td>{r.org_name}</td>
                    <td>{r.synthetic_patient_ref}</td>
                    <td className="num">{r.qty}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </>
  )
}
