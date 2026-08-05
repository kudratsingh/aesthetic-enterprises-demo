import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import './App.css'

function App() {
  const [token, setToken] = useState<string | null>(null)

  const health = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/health')
      if (error !== undefined) throw new Error('health check failed')
      return data
    },
  })

  const signIn = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/auth/dev-token', {
        body: { role: 'hq_admin', org_id: 'org-hq', sub: 'dev-user' },
      })
      if (error !== undefined || data === undefined)
        throw new Error('sign-in failed')
      return data.access_token
    },
    onSuccess: setToken,
  })

  const hello = useQuery({
    queryKey: ['hello', token],
    enabled: token !== null,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/hello', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (error !== undefined) throw new Error('hello round trip failed')
      return data
    },
  })

  return (
    <main className="card">
      <h1>clinic-network-os</h1>
      <p className="subtitle">Phase 0 — walking skeleton</p>

      <section>
        <h2>API health</h2>
        {health.isPending && <p>checking…</p>}
        {health.isError && (
          <p className="bad">unreachable — is the API running? (make dev)</p>
        )}
        {health.isSuccess && <p className="good">{health.data.status}</p>}
      </section>

      <section>
        <h2>Round trip (web → api → db)</h2>
        {token === null ? (
          <button onClick={() => signIn.mutate()} disabled={signIn.isPending}>
            Sign in (dev token)
          </button>
        ) : hello.isSuccess ? (
          <>
            <p className="good">{hello.data.message}</p>
            <p>
              db time: {new Date(hello.data.db_time).toLocaleString()} · env:{' '}
              {hello.data.environment}
            </p>
          </>
        ) : hello.isError ? (
          <p className="bad">round trip failed</p>
        ) : (
          <p>calling…</p>
        )}
        {signIn.isError && <p className="bad">sign-in failed</p>}
      </section>
    </main>
  )
}

export default App
