import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../auth/useAuth'
import { useLocations } from '../royalty/api'
import { useLots, useProducts } from '../supply/api'
import {
  useCreateOrder,
  useFulfillOrder,
  useOrders,
  useSubmitOrder,
} from './api'

export function OrdersPage() {
  const { claims } = useAuth()
  const isHq = claims?.role === 'hq_admin'
  const orders = useOrders()
  const products = useProducts()
  const lots = useLots()
  const locations = useLocations()
  const create = useCreateOrder()
  const submit = useSubmitOrder()
  const fulfill = useFulfillOrder()

  const [locationId, setLocationId] = useState('')
  const [productId, setProductId] = useState('')
  const [qty, setQty] = useState('10')
  // HQ fulfillment: chosen lot per (order, product)
  const [lotChoice, setLotChoice] = useState<Record<string, string>>({})

  const onCreate = (e: FormEvent) => {
    e.preventDefault()
    const loc = locationId !== '' ? locationId : (locations.data?.[0]?.id ?? '')
    const product =
      productId !== '' ? productId : (products.data?.[0]?.id ?? '')
    const n = Number(qty)
    if (loc === '' || product === '' || !Number.isInteger(n) || n <= 0) return
    create.mutate({
      location_id: loc,
      lines: [{ product_id: product, qty: n }],
    })
  }

  const fulfillOrder = (orderId: string, lines: { product_id: string }[]) => {
    const assignments = lines.map((line) => {
      const chosen = lotChoice[`${orderId}:${line.product_id}`]
      const fallback = lots.data?.find(
        (l) => l.product_id === line.product_id,
      )?.id
      return { product_id: line.product_id, lot_id: chosen ?? fallback ?? '' }
    })
    if (assignments.some((a) => a.lot_id === '')) return
    fulfill.mutate({ orderId, assignments })
  }

  return (
    <>
      <h1>{isHq ? 'Product orders — fulfillment' : 'Product orders'}</h1>

      {!isHq && (
        <section className="panel">
          <h2>New order</h2>
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
              inputMode="numeric"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
            <button type="submit" disabled={create.isPending}>
              Create draft order
            </button>
          </form>
        </section>
      )}

      {orders.isPending && <p className="hint">loading…</p>}
      {orders.isSuccess && orders.data.length === 0 && (
        <p className="hint">No orders yet.</p>
      )}

      {(orders.data ?? []).map((o) => (
        <section key={o.id} className="panel">
          <h2>
            {o.location_name} <span className="hint">({o.org_name})</span>{' '}
            <span
              className={`badge b-${o.status === 'fulfilled' ? 'paid' : o.status === 'submitted' ? 'submitted' : 'draft'}`}
            >
              {o.status}
            </span>
          </h2>
          <table className="tbl">
            <tbody>
              {o.lines.map((line) => (
                <tr key={line.product_id}>
                  <td>{line.product_name}</td>
                  <td className="num">qty {line.qty}</td>
                  <td>
                    {isHq && o.status === 'submitted' && (
                      <select
                        value={
                          lotChoice[`${o.id}:${line.product_id}`] ??
                          lots.data?.find(
                            (l) => l.product_id === line.product_id,
                          )?.id ??
                          ''
                        }
                        onChange={(e) =>
                          setLotChoice({
                            ...lotChoice,
                            [`${o.id}:${line.product_id}`]: e.target.value,
                          })
                        }
                      >
                        {(lots.data ?? [])
                          .filter((l) => l.product_id === line.product_id)
                          .map((l) => (
                            <option key={l.id} value={l.id}>
                              {l.lot_code} (exp {l.expiry})
                            </option>
                          ))}
                      </select>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row-form">
            {!isHq && o.status === 'draft' && (
              <button
                disabled={submit.isPending}
                onClick={() => submit.mutate(o.id)}
              >
                Submit order
              </button>
            )}
            {isHq && o.status === 'submitted' && (
              <button
                disabled={fulfill.isPending}
                onClick={() => fulfillOrder(o.id, o.lines)}
              >
                Fulfill → ship from lots
              </button>
            )}
            {o.status === 'fulfilled' && (
              <span className="good">
                shipped into the ledger
                {o.fulfilled_at !== null &&
                  ` · ${new Date(o.fulfilled_at).toLocaleString()}`}
              </span>
            )}
          </div>
        </section>
      ))}
      {fulfill.isError && (
        <p className="bad">fulfillment failed (check lot/product match)</p>
      )}
    </>
  )
}
