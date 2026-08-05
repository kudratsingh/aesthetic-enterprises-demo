import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import './App.css'

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [email, setEmail] = useState('hq_admin@clinic-network-os.demo')
  const [password, setPassword] = useState('')

  const health = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/health')
      if (error !== undefined) throw new Error('health check failed')
      return data
    },
  })

  const signIn = useMutation({
    mutationFn: async (creds: { email: string; password: string }) => {
      const { data, error } = await api.POST('/api/v1/auth/login', {
        body: creds,
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

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    signIn.mutate({ email, password })
  }

  return (
    <main className="card">
      <h1>clinic-network-os</h1>
      <p className="subtitle">Phase 1 — tenancy, auth, schema</p>

      <section>
        <h2>API health</h2>
        {health.isPending && <p>checking…</p>}
        {health.isError && (
          <p className="bad">unreachable — is the API running? (make dev)</p>
        )}
        {health.isSuccess && <p className="good">{health.data.status}</p>}
      </section>

      <section>
        <h2>Sign in</h2>
        {token === null ? (
          <form onSubmit={onSubmit} className="login">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email"
              autoComplete="username"
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="password"
              autoComplete="current-password"
            />
            <button type="submit" disabled={signIn.isPending}>
              Sign in
            </button>
            {signIn.isError && <p className="bad">invalid email or password</p>}
            <p className="hint">
              Seeded demo users: see docs/runbooks/local-dev.md
            </p>
          </form>
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
      </section>
    </main>
  )
}

export default App
