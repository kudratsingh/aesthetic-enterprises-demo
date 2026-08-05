import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthContext'
import { LoginPage } from './features/auth/LoginPage'
import { RequireRole } from './features/auth/RequireRole'
import { HomePage } from './features/home/HomePage'
import { Placeholder } from './features/royalty/Placeholder'
import { Shell } from './components/Shell'
import './App.css'

const HQ_NAV = [
  { to: '/hq', label: 'Home' },
  { to: '/hq/royalty', label: 'Royalty runs' },
  { to: '/hq/invoices', label: 'Invoices & aging' },
]

const OPERATOR_NAV = [
  { to: '/operator', label: 'Home' },
  { to: '/operator/reports', label: 'Monthly reports' },
  { to: '/operator/statements', label: 'Statements & invoices' },
]

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireRole roles={['hq_admin']} />}>
          <Route element={<Shell title="HQ" nav={HQ_NAV} />}>
            <Route path="/hq" element={<HomePage />} />
            <Route
              path="/hq/royalty"
              element={<Placeholder title="Royalty runs" />}
            />
            <Route
              path="/hq/invoices"
              element={<Placeholder title="Invoices & aging" />}
            />
          </Route>
        </Route>

        <Route element={<RequireRole roles={['operator', 'clinic_staff']} />}>
          <Route element={<Shell title="Operator" nav={OPERATOR_NAV} />}>
            <Route path="/operator" element={<HomePage />} />
            <Route
              path="/operator/reports"
              element={<Placeholder title="Monthly reports" />}
            />
            <Route
              path="/operator/statements"
              element={<Placeholder title="Statements & invoices" />}
            />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
