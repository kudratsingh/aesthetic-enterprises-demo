import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useAuthHeaders } from '../auth/useAuth'

export type Payment = components['schemas']['PaymentOut']
export type Checkout = components['schemas']['CheckoutOut']
export type PaymentResult = components['schemas']['PaymentResultOut']

function fail(what: string): never {
  throw new Error(`${what} failed`)
}

export function usePayments() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['payments'],
    queryFn: async (): Promise<Payment[]> => {
      const { data, error } = await api.GET('/api/v1/collections/payments', {
        headers,
      })
      if (error !== undefined || data === undefined) fail('loading payments')
      return data
    },
  })
}

/**
 * The mock collection flow in one action: open a checkout session for the
 * invoice, then simulate the provider's redirect completion (ADR-0010). With
 * a real provider the second step is the payer finishing hosted checkout and
 * the provider calling /webhooks/payments — the UI never computes signatures.
 */
export function useCollectInvoice() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (invoiceId: string): Promise<PaymentResult> => {
      const checkout = await api.POST(
        '/api/v1/collections/invoices/{invoice_id}/checkout',
        {
          headers,
          params: { path: { invoice_id: invoiceId } },
        },
      )
      if (checkout.error !== undefined || checkout.data === undefined)
        fail('creating checkout')
      const simulated = await api.POST(
        '/api/v1/collections/payments/{payment_id}/simulate',
        {
          headers,
          params: { path: { payment_id: checkout.data.payment.id } },
        },
      )
      if (simulated.error !== undefined || simulated.data === undefined)
        fail('completing mock payment')
      return simulated.data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['invoices'] })
      void qc.invalidateQueries({ queryKey: ['aging'] })
      void qc.invalidateQueries({ queryKey: ['payments'] })
    },
  })
}
