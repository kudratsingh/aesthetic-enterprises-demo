import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthContext'
import { LoginPage } from './features/auth/LoginPage'
import { RequireRole } from './features/auth/RequireRole'
import { HomePage } from './features/home/HomePage'
import { DocumentsPage } from './features/portal/DocumentsPage'
import { OnboardingPage } from './features/portal/OnboardingPage'
import { OrdersPage } from './features/portal/OrdersPage'
import { DashboardPage } from './features/kpi/DashboardPage'
import { HqInvoicesPage } from './features/royalty/HqInvoicesPage'
import { HqRoyaltyRunsPage } from './features/royalty/HqRoyaltyRunsPage'
import { OperatorReportsPage } from './features/royalty/OperatorReportsPage'
import { OperatorStatementsPage } from './features/royalty/OperatorStatementsPage'
import { SupplyPage } from './features/supply/SupplyPage'
import { VariancePage } from './features/variance/VariancePage'
import { Shell } from './components/Shell'
import './App.css'

const HQ_NAV = [
  { to: '/hq', label: 'Dashboard' },
  { to: '/hq/royalty', label: 'Royalty runs' },
  { to: '/hq/invoices', label: 'Invoices & aging' },
  { to: '/hq/variance', label: 'Variance' },
  { to: '/hq/supply', label: 'Traceability' },
  { to: '/hq/orders', label: 'Orders' },
  { to: '/hq/onboarding', label: 'Onboarding' },
]

const OPERATOR_NAV = [
  { to: '/operator', label: 'Home' },
  { to: '/operator/reports', label: 'Monthly reports' },
  { to: '/operator/statements', label: 'Statements & invoices' },
  { to: '/operator/supply', label: 'Supply' },
  { to: '/operator/orders', label: 'Orders' },
  { to: '/operator/onboarding', label: 'Onboarding' },
  { to: '/operator/documents', label: 'Documents' },
]

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireRole roles={['hq_admin']} />}>
          <Route element={<Shell title="HQ" nav={HQ_NAV} />}>
            <Route path="/hq" element={<DashboardPage />} />
            <Route path="/hq/royalty" element={<HqRoyaltyRunsPage />} />
            <Route path="/hq/invoices" element={<HqInvoicesPage />} />
            <Route path="/hq/variance" element={<VariancePage />} />
            <Route path="/hq/supply" element={<SupplyPage />} />
            <Route path="/hq/orders" element={<OrdersPage />} />
            <Route path="/hq/onboarding" element={<OnboardingPage />} />
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
            <Route path="/operator/supply" element={<SupplyPage />} />
            <Route path="/operator/orders" element={<OrdersPage />} />
            <Route path="/operator/onboarding" element={<OnboardingPage />} />
            <Route path="/operator/documents" element={<DocumentsPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
