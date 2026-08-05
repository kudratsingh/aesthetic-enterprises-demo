import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useAuthHeaders } from '../auth/useAuth'

export type OnboardingTask = components['schemas']['OnboardingTaskOut']
export type PortalDocument = components['schemas']['DocumentOut']
export type Order = components['schemas']['OrderOut']

function fail(what: string): never {
  throw new Error(`${what} failed`)
}

export function useOnboarding() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['onboarding'],
    queryFn: async (): Promise<OnboardingTask[]> => {
      const { data, error } = await api.GET('/api/v1/portal/onboarding', {
        headers,
      })
      if (error !== undefined || data === undefined) fail('loading onboarding')
      return data
    },
  })
}

export function useCompleteTask() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (taskId: string) => {
      const { data, error } = await api.POST(
        '/api/v1/portal/onboarding/{task_id}/complete',
        {
          headers,
          params: { path: { task_id: taskId } },
        },
      )
      if (error !== undefined || data === undefined) fail('completing task')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['onboarding'] }),
  })
}

export function useDocuments() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['documents'],
    queryFn: async (): Promise<PortalDocument[]> => {
      const { data, error } = await api.GET('/api/v1/portal/documents', {
        headers,
      })
      if (error !== undefined || data === undefined) fail('loading documents')
      return data
    },
  })
}

export function useCreateDocument() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['DocumentCreate']) => {
      const { data, error } = await api.POST('/api/v1/portal/documents', {
        headers,
        body,
      })
      if (error !== undefined || data === undefined) fail('creating document')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['documents'] }),
  })
}

export function useOrders() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['orders'],
    queryFn: async (): Promise<Order[]> => {
      const { data, error } = await api.GET('/api/v1/portal/orders', {
        headers,
      })
      if (error !== undefined || data === undefined) fail('loading orders')
      return data
    },
  })
}

export function useCreateOrder() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (
      body: components['schemas']['OrderCreate'],
    ): Promise<Order> => {
      const { data, error } = await api.POST('/api/v1/portal/orders', {
        headers,
        body,
      })
      if (error !== undefined || data === undefined) fail('creating order')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['orders'] }),
  })
}

export function useSubmitOrder() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (orderId: string): Promise<Order> => {
      const { data, error } = await api.POST(
        '/api/v1/portal/orders/{order_id}/submit',
        {
          headers,
          params: { path: { order_id: orderId } },
        },
      )
      if (error !== undefined || data === undefined) fail('submitting order')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['orders'] }),
  })
}

export function useFulfillOrder() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      orderId: string
      assignments: { product_id: string; lot_id: string }[]
    }): Promise<Order> => {
      const { data, error } = await api.POST(
        '/api/v1/portal/orders/{order_id}/fulfill',
        {
          headers,
          params: { path: { order_id: input.orderId } },
          body: { assignments: input.assignments },
        },
      )
      if (error !== undefined || data === undefined) fail('fulfilling order')
      return data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['orders'] })
      void qc.invalidateQueries({ queryKey: ['on-hand'] })
    },
  })
}
