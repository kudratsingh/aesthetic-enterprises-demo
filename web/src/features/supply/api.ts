import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useAuthHeaders } from '../auth/useAuth'

export type Product = components['schemas']['ProductOut']
export type Lot = components['schemas']['LotOut']
export type OnHandRow = components['schemas']['OnHandRow']
export type Recall = components['schemas']['RecallResponse']

export function useProducts() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['products'],
    queryFn: async (): Promise<Product[]> => {
      const { data, error } = await api.GET('/api/v1/supply/products', {
        headers,
      })
      if (error !== undefined || data === undefined)
        throw new Error('loading products failed')
      return data
    },
  })
}

export function useLots() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['lots'],
    queryFn: async (): Promise<Lot[]> => {
      const { data, error } = await api.GET('/api/v1/supply/lots', { headers })
      if (error !== undefined || data === undefined)
        throw new Error('loading lots failed')
      return data
    },
  })
}

export function useOnHand() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['on-hand'],
    queryFn: async (): Promise<OnHandRow[]> => {
      const { data, error } = await api.GET('/api/v1/supply/on-hand', {
        headers,
      })
      if (error !== undefined || data === undefined)
        throw new Error('loading on-hand failed')
      return data
    },
  })
}

export function useReceiveLot() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['ReceiveLotRequest']) => {
      const { data, error } = await api.POST('/api/v1/supply/lots', {
        headers,
        body,
      })
      if (error !== undefined || data === undefined)
        throw new Error('receiving lot failed')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['lots'] }),
  })
}

export function useShip() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['ShipRequest']) => {
      const { data, error } = await api.POST('/api/v1/supply/shipments', {
        headers,
        body,
      })
      if (error !== undefined || data === undefined)
        throw new Error('shipping failed')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['on-hand'] }),
  })
}

export type AdministerError = 'expired_lot' | 'insufficient_stock' | 'other'

export function useAdminister() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['AdministerRequest']) => {
      const { data, error, response } = await api.POST(
        '/api/v1/supply/administrations',
        {
          headers,
          body,
        },
      )
      if (error !== undefined || data === undefined) {
        const kind: AdministerError =
          response.status === 422
            ? 'expired_lot'
            : response.status === 409
              ? 'insufficient_stock'
              : 'other'
        throw new Error(kind)
      }
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['on-hand'] }),
  })
}

export function useRecall(lotId: string | null) {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['recall', lotId],
    enabled: lotId !== null,
    queryFn: async (): Promise<Recall> => {
      const { data, error } = await api.GET('/api/v1/supply/recall/{lot_id}', {
        headers,
        params: { path: { lot_id: lotId ?? '' } },
      })
      if (error !== undefined || data === undefined)
        throw new Error('recall query failed')
      return data
    },
  })
}
