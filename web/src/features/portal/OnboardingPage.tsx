import { useAuth } from '../auth/useAuth'
import { useCompleteTask, useOnboarding } from './api'

export function OnboardingPage() {
  const { claims } = useAuth()
  const isHq = claims?.role === 'hq_admin'
  const onboarding = useOnboarding()
  const complete = useCompleteTask()

  const tasks = onboarding.data ?? []
  const byOrg = new Map<string, typeof tasks>()
  for (const t of tasks) {
    byOrg.set(t.org_name, [...(byOrg.get(t.org_name) ?? []), t])
  }

  return (
    <>
      <h1>{isHq ? 'Onboarding — network view' : '60-day onboarding'}</h1>
      {onboarding.isPending && <p className="hint">loading…</p>}
      {[...byOrg.entries()].map(([orgName, orgTasks]) => {
        const done = orgTasks.filter((t) => t.completed_at !== null).length
        return (
          <section key={orgName} className="panel">
            <h2>
              {isHq ? orgName : 'Checklist'}{' '}
              <span className="hint">
                {done}/{orgTasks.length} complete
              </span>
            </h2>
            <div className="progress">
              <div
                className="progress-fill"
                style={{ width: `${(done / orgTasks.length) * 100}%` }}
              />
            </div>
            <table className="tbl">
              <tbody>
                {orgTasks.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <span className={t.completed_at !== null ? 'good' : ''}>
                        {t.completed_at !== null ? '✓ ' : ''}
                        {t.title}
                      </span>
                    </td>
                    <td className="hint">{t.category}</td>
                    <td className="hint">day {t.due_offset_days}</td>
                    <td>
                      {t.completed_at === null && !isHq && (
                        <button
                          disabled={complete.isPending}
                          onClick={() => complete.mutate(t.id)}
                        >
                          Mark complete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )
      })}
    </>
  )
}
