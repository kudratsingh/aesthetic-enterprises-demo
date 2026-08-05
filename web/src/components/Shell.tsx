import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../features/auth/useAuth'

export interface NavItem {
  to: string
  label: string
}

/** Shared chrome for the role shells: top bar, nav, content outlet. */
export function Shell({ title, nav }: { title: string; nav: NavItem[] }) {
  const { claims, logout } = useAuth()
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">clinic-network-os</span>
        <span className="shell-title">{title}</span>
        <span className="spacer" />
        <span className="whoami">{claims?.role}</span>
        <button onClick={logout}>Sign out</button>
      </header>
      <nav className="sidenav">
        {nav.map((item) => (
          <NavLink key={item.to} to={item.to} end>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
