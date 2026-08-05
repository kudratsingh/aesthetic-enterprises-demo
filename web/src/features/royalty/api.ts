import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { useAuthHeaders } from '../auth/useAuth'

export type RevenueReport = components['schemas']['RevenueReportOut']
export type RoyaltyRun = components['schemas']['RoyaltyRunOut']
export type RunSummary = components['schemas']['RoyaltyRunSummaryOut']
export type LineItem = components['schemas']['RoyaltyLineItemOut']
export type Invoice = components['schemas']['InvoiceOut']
export type Aging = components['schemas']['AgingOut']
export type Location = components['schemas']['LocationOut']

function fail(what: string): never {
  throw new Error(`${what} failed`)
}

export function useLocations() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['locations'],
    queryFn: async (): Promise<Location[]> => {
      const { data, error } = await api.GET('/api/v1/locations', { headers })
      if (error !== undefined || data === undefined) fail('loading locations')
      return data
    },
  })
}

/** location_id → display name, org_id → org name. */
export function locationMaps(locations: Location[] | undefined) {
  const locName = new Map<string, string>()
  const orgName = new Map<string, string>()
  for (const l of locations ?? []) {
    locName.set(l.id, l.name)
    orgName.set(l.org_id, l.org_name)
  }
  return { locName, orgName }
}

export function useReports() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['reports'],
    queryFn: async (): Promise<RevenueReport[]> => {
      const { data, error } = await api.GET('/api/v1/royalty/reports', {
        headers,
      })
      if (error !== undefined || data === undefined) fail('loading reports')
      return data
    },
  })
}

export function useCreateReport() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['RevenueReportCreate']) => {
      const { data, error } = await api.POST('/api/v1/royalty/reports', {
        headers,
        body,
      })
      if (error !== undefined || data === undefined) fail('creating report')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['reports'] }),
  })
}

export function useSubmitReport() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (reportId: string) => {
      const { data, error } = await api.POST(
        '/api/v1/royalty/reports/{report_id}/submit',
        {
          headers,
          params: { path: { report_id: reportId } },
        },
      )
      if (error !== undefined || data === undefined) fail('submitting report')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['reports'] }),
  })
}

export function useCreateCorrection() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (reportId: string) => {
      const { data, error } = await api.POST(
        '/api/v1/royalty/reports/{report_id}/corrections',
        {
          headers,
          params: { path: { report_id: reportId } },
        },
      )
      if (error !== undefined || data === undefined) fail('creating correction')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['reports'] }),
  })
}

export function useRuns() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['runs'],
    queryFn: async (): Promise<RunSummary[]> => {
      const { data, error } = await api.GET('/api/v1/royalty/runs', { headers })
      if (error !== undefined || data === undefined) fail('loading runs')
      return data
    },
  })
}

export function useRunPeriod() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (period: string): Promise<RoyaltyRun> => {
      const { data, error } = await api.POST('/api/v1/royalty/runs', {
        headers,
        body: { period },
      })
      if (error !== undefined || data === undefined) fail('running period')
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['runs'] }),
  })
}

export function useLineItems(runId: string | null) {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['line-items', runId],
    enabled: runId !== null,
    queryFn: async (): Promise<LineItem[]> => {
      const { data, error } = await api.GET(
        '/api/v1/royalty/runs/{run_id}/line-items',
        {
          headers,
          params: { path: { run_id: runId ?? '' } },
        },
      )
      if (error !== undefined || data === undefined) fail('loading line items')
      return data
    },
  })
}

export function useInvoices() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['invoices'],
    queryFn: async (): Promise<Invoice[]> => {
      const { data, error } = await api.GET('/api/v1/royalty/invoices', {
        headers,
      })
      if (error !== undefined || data === undefined) fail('loading invoices')
      return data
    },
  })
}

export function useIssueInvoices() {
  const headers = useAuthHeaders()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (
      runId: string,
    ): Promise<components['schemas']['IssueInvoicesOut']> => {
      const { data, error } = await api.POST(
        '/api/v1/royalty/runs/{run_id}/invoices',
        {
          headers,
          params: { path: { run_id: runId } },
        },
      )
      if (error !== undefined || data === undefined) fail('issuing invoices')
      return data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['invoices'] })
      void qc.invalidateQueries({ queryKey: ['aging'] })
    },
  })
}

export function useAging() {
  const headers = useAuthHeaders()
  return useQuery({
    queryKey: ['aging'],
    queryFn: async (): Promise<Aging> => {
      const { data, error } = await api.GET('/api/v1/royalty/invoices/aging', {
        headers,
      })
      if (error !== undefined || data === undefined) fail('loading aging')
      return data
    },
  })
}
