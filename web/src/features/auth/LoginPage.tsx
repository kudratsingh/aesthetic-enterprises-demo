import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from './useAuth'

export function LoginPage() {
  const { claims, login } = useAuth()
  const [email, setEmail] = useState('hq_admin@clinic-network-os.demo')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(false)
  const [pending, setPending] = useState(false)

  if (claims !== null) {
    return (
      <Navigate to={claims.role === 'hq_admin' ? '/hq' : '/operator'} replace />
    )
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setPending(true)
    setError(false)
    login(email, password)
      .catch(() => setError(true))
      .finally(() => setPending(false))
  }

  return (
    <main className="card">
      <h1>clinic-network-os</h1>
      <p className="subtitle">
        Network royalty, KPI &amp; traceability — demo (synthetic data)
      </p>
      <section>
        <h2>Sign in</h2>
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
          <button type="submit" disabled={pending}>
            Sign in
          </button>
          {error && <p className="bad">invalid email or password</p>}
          <p className="hint">Demo logins: docs/runbooks/local-dev.md</p>
        </form>
      </section>
    </main>
  )
}
