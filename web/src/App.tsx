import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthContext'
import { LoginPage } from './features/auth/LoginPage'
import { RequireRole } from './features/auth/RequireRole'
import { HomePage } from './features/home/HomePage'
import { HqInvoicesPage } from './features/royalty/HqInvoicesPage'
import { HqRoyaltyRunsPage } from './features/royalty/HqRoyaltyRunsPage'
import { OperatorReportsPage } from './features/royalty/OperatorReportsPage'
import { OperatorStatementsPage } from './features/royalty/OperatorStatementsPage'
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
            <Route path="/hq/royalty" element={<HqRoyaltyRunsPage />} />
            <Route path="/hq/invoices" element={<HqInvoicesPage />} />
          </Route>
        </Route>

        <Route element={<RequireRole roles={['operator', 'clinic_staff']} />}>
          <Route element={<Shell title="Operator" nav={OPERATOR_NAV} />}>
            <Route path="/operator" element={<HomePage />} />
            <Route path="/operator/reports" element={<OperatorReportsPage />} />
            <Route
              path="/operator/statements"
              element={<OperatorStatementsPage />}
            />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
