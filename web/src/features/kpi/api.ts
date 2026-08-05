import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useAuthHeaders } from '../auth/useAuth'

export type NetworkKpis = components['schemas']['NetworkPeriodKpis']
export type LocationKpis = components['schemas']['LocationKpiRow']

export function useNetworkKpis(months = 6) {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['kpi-network', months],
    queryFn: async (): Promise<NetworkKpis[]> => {
      const { data, error } = await api.GET('/api/v1/kpi/network', {
        headers,
        params: { query: { months } },
      })
      if (error !== undefined || data === undefined)
        throw new Error('loading network KPIs failed')
      return data
    },
  })
}

export function useLocationKpis(period: string) {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['kpi-locations', period],
    queryFn: async (): Promise<LocationKpis[]> => {
      const { data, error } = await api.GET('/api/v1/kpi/locations', {
        headers,
        params: { query: { period } },
      })
      if (error !== undefined || data === undefined)
        throw new Error('loading location KPIs failed')
      return data
    },
  })
}
