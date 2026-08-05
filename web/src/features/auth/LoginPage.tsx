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
          <div className="row-form">
            <button
              type="button"
              onClick={() => {
                setEmail('hq_admin@clinic-network-os.demo')
                setPassword('demo-hq-2026!')
              }}
            >
              Fill HQ demo login
            </button>
            <button
              type="button"
              onClick={() => {
                setEmail('operator-1@clinic-network-os.demo')
                setPassword('demo-operator-2026!')
              }}
            >
              Fill operator demo login
            </button>
          </div>
          <p className="hint">
            Synthetic demo credentials — all data in this system is fabricated.
          </p>
        </form>
      </section>
    </main>
  )
}
