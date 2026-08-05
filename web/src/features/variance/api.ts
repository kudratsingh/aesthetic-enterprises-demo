import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useAuthHeaders } from '../auth/useAuth'

export type VarianceFlag = components['schemas']['VarianceFlagOut']
export type ComputeResult = components['schemas']['ComputeVarianceResponse']

export function useVarianceFlags(period: string | null) {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['variance-flags', period],
    queryFn: async (): Promise<VarianceFlag[]> => {
      const { data, error } = await api.GET('/api/v1/variance/flags', {
        headers,
        params: { query: period === null ? {} : { period } },
      })
      if (error !== undefined || data === undefined)
        throw new Error('loading flags failed')
      return data
    },
  })
}

export function useComputeVariance() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (period: string): Promise<ComputeResult> => {
      const { data, error } = await api.POST('/api/v1/variance/compute', {
        headers,
        params: { query: { period } },
      })
      if (error !== undefined || data === undefined)
        throw new Error('variance compute failed')
      return data
    },
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ['variance-flags'] }),
  })
}

export function useResolveFlag() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      flagId: string
      status: 'reviewed' | 'resolved'
      reason: string | null
    }) => {
      const { data, error } = await api.POST(
        '/api/v1/variance/flags/{flag_id}/resolve',
        {
          headers,
          params: { path: { flag_id: input.flagId } },
          body: { status: input.status, reason: input.reason },
        },
      )
      if (error !== undefined || data === undefined)
        throw new Error('resolving flag failed')
      return data
    },
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ['variance-flags'] }),
  })
}
