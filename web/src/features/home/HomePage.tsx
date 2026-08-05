import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { useAuth, useAuthHeaders } from '../auth/useAuth'

/** Landing page for both shells: identity + live api→db round-trip check. */
export function HomePage() {
  const { claims } = useAuth()
  const headers = useAuthHeaders()

  const hello = useQuery({
    queryKey: ['hello', claims?.sub],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/hello', { headers })
      if (error !== undefined) throw new Error('round trip failed')
      return data
    },
  })

  return (
    <>
      <h1>Welcome</h1>
      <p>
        Signed in as <strong>{claims?.role}</strong> (org{' '}
        {claims?.org_id.slice(0, 8)}…)
      </p>
      {hello.isSuccess && (
        <p className="good">
          {hello.data.message} · db time{' '}
          {new Date(hello.data.db_time).toLocaleString()}
        </p>
      )}
      {hello.isError && <p className="bad">api round trip failed</p>}
    </>
  )
}
