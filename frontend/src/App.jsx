import React, { useEffect, useState } from 'react'
import { Route, Routes, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { api, login as loginRequest, logoutRequest, mfaConfirm, mfaSetup, mfaVerify, setToken } from './api.js'
import Layout from './components/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Login from './pages/Login.jsx'
import WorkOrders from './pages/WorkOrders.jsx'
import WorkOrderArchives from './pages/WorkOrderArchives.jsx'
import Assets from './pages/Assets.jsx'
import AssetDetail from './pages/AssetDetail.jsx'
import AssetForm from './pages/AssetForm.jsx'
import Customers from './pages/Customers.jsx'
import Materials from './pages/Materials.jsx'
import Users from './pages/Users.jsx'
import Settings from './pages/Settings.jsx'
import AuditLogs from './pages/AuditLogs.jsx'
import Backups from './pages/Backups.jsx'
import ChangePassword from './pages/ChangePassword.jsx'
import ModuleSelector from './pages/ModuleSelector.jsx'
import HrHome from './pages/HrHome.jsx'
import HrLeave from './pages/HrLeave.jsx'
import HrApprovals from './pages/HrApprovals.jsx'
import HrSummary from './pages/HrSummary.jsx'
import HrAdmin from './pages/HrAdmin.jsx'
import CrmHome from './pages/CrmHome.jsx'
import CrmCustomers from './pages/CrmCustomers.jsx'
import CrmCustomerDetail from './pages/CrmCustomerDetail.jsx'
import CrmOpportunities from './pages/CrmOpportunities.jsx'
import CrmActivities from './pages/CrmActivities.jsx'
import CrmContracts from './pages/CrmContracts.jsx'
import Notifications from './pages/Notifications.jsx'
import ServiceReports from './pages/ServiceReports.jsx'
import HrReports from './pages/HrReports.jsx'
import CrmReports from './pages/CrmReports.jsx'
import ProcurementRequests from './pages/ProcurementRequests.jsx'
import ProcurementNew from './pages/ProcurementNew.jsx'
import ProcurementDetail from './pages/ProcurementDetail.jsx'
import ProcurementApprovals from './pages/ProcurementApprovals.jsx'
import { hasModule, hasPermission } from './utils/permissions.js'


function PermissionRoute({ user, permission, children, fallback = '/hr' }) {
  return hasPermission(user, permission) ? children : <Navigate to={fallback} replace />
}

function AdminRoleRoute({ user, children }) {
  if (user?.role?.name === 'Admin') return children
  if (hasPermission(user, 'admin.backup.manage')) return <Navigate to="/admin/backups" replace />
  return <Navigate to="/modules" replace />
}

function AdminIndex({ user }) {
  if (hasPermission(user, 'admin.backup.manage')) return <Navigate to="/admin/backups" replace />
  if (user?.role?.name === 'Admin') return <Navigate to="/admin/users" replace />
  return <Navigate to="/modules" replace />
}

function LegacyServiceRedirect() {
  const location = useLocation()
  const legacyPath = location.pathname === '/work-order-archives' ? '/work-orders/archives' : location.pathname
  return <Navigate to={`/service${legacyPath}${location.search}${location.hash}`} replace />
}

function LegacyAdminRedirect() {
  const location = useLocation()
  return <Navigate to={`/admin${location.pathname}${location.search}${location.hash}`} replace />
}

function moduleForPath(pathname) {
  if (pathname.startsWith('/service') || pathname.startsWith('/work-orders') || pathname.startsWith('/work-order-archives') || pathname.startsWith('/assets') || pathname.startsWith('/customers') || pathname.startsWith('/materials')) return 'service'
  if (pathname.startsWith('/hr')) return 'hr'
  if (pathname.startsWith('/crm')) return 'crm'
  if (pathname.startsWith('/procurement')) return 'procurement'
  if (pathname.startsWith('/notifications')) return null
  if (pathname.startsWith('/admin') || pathname === '/users' || pathname === '/settings') return 'admin'
  return null
}

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [appInfo, setAppInfo] = useState(null)
  const location = useLocation()
  const navigate = useNavigate()

  async function refreshUser() {
    try {
      const me = await api('/auth/me')
      setUser(me)
      return me
    } catch {
      setToken(null)
      setUser(null)
      return null
    }
  }

  useEffect(() => {
    api('/version').then((info) => {
      setAppInfo(info)
      document.title = `${info.application} v${info.version}`
    }).catch(() => {})
    refreshUser().finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const permissionsHandler = () => refreshUser()
    const expiredHandler = () => { setUser(null); navigate('/', { replace: true }) }
    window.addEventListener('app:permissions-changed', permissionsHandler)
    window.addEventListener('app:session-expired', expiredHandler)
    return () => {
      window.removeEventListener('app:permissions-changed', permissionsHandler)
      window.removeEventListener('app:session-expired', expiredHandler)
    }
  }, [])

  async function finishAuthentication() {
    const me = await api('/auth/me')
    setUser(me)
    if (!me.must_change_password) navigate('/modules', { replace: true })
    return me
  }

  async function handleLogin(email, password) {
    const data = await loginRequest(email, password)
    if (data.mfa_setup_required || data.mfa_required) return data
    await finishAuthentication()
    return data
  }

  async function handleMfaSetup(challengeToken) {
    return mfaSetup(challengeToken)
  }

  async function handleMfaConfirm(challengeToken, code) {
    return mfaConfirm(challengeToken, code)
  }

  async function handleMfaVerify(challengeToken, code) {
    const data = await mfaVerify(challengeToken, code)
    await finishAuthentication()
    return data
  }

  async function handleMfaSetupFinished() {
    return finishAuthentication()
  }

  async function logout() {
    try { await logoutRequest() } catch { /* local logout still proceeds */ }
    setToken(null)
    setUser(null)
    navigate('/', { replace: true })
  }

  if (loading) return <div className="center">Betöltés...</div>
  if (!user) return (
    <Login
      onLogin={handleLogin}
      onMfaSetup={handleMfaSetup}
      onMfaConfirm={handleMfaConfirm}
      onMfaVerify={handleMfaVerify}
      onMfaSetupFinished={handleMfaSetupFinished}
    />
  )
  if (user.must_change_password) {
    return <ChangePassword forced onChanged={(updated) => { setUser(updated); navigate('/modules', { replace: true }) }} onLogout={logout} />
  }

  if (location.pathname === '/' || location.pathname === '') return <Navigate to="/modules" replace />
  if (location.pathname === '/modules') return <ModuleSelector user={user} appInfo={appInfo} onLogout={logout} />

  if (location.pathname === '/change-password') {
    return (
      <Layout user={user} onLogout={logout} appInfo={appInfo} currentModule={null}>
        <ChangePassword onChanged={setUser} />
      </Layout>
    )
  }

  const currentModule = moduleForPath(location.pathname)
  if (currentModule && !hasModule(user, currentModule)) return <Navigate to="/modules" replace />

  return (
    <Layout user={user} onLogout={logout} appInfo={appInfo} currentModule={currentModule}>
      <Routes>
        <Route path="/service" element={<Dashboard />} />
        <Route path="/service/work-orders" element={<WorkOrders user={user} mode="list" />} />
        <Route path="/service/work-orders/archives" element={<WorkOrderArchives user={user} />} />
        <Route path="/service/work-orders/new" element={<WorkOrders user={user} mode="create" />} />
        <Route path="/service/work-orders/:workOrderId/edit" element={<WorkOrders user={user} mode="edit" />} />
        <Route path="/service/work-orders/:workOrderId/close" element={<WorkOrders user={user} mode="close" />} />
        <Route path="/service/work-orders/:workOrderId" element={<WorkOrders user={user} mode="detail" />} />
        <Route path="/service/work-order-archives" element={<Navigate to="/service/work-orders/archives" replace />} />
        <Route path="/service/assets/new" element={<AssetForm user={user} />} />
        <Route path="/service/assets/:assetId/edit" element={<AssetForm user={user} />} />
        <Route path="/service/assets/:assetId" element={<AssetDetail user={user} />} />
        <Route path="/service/assets" element={<Assets user={user} />} />
        <Route path="/service/customers" element={<Customers user={user} />} />
        <Route path="/service/materials" element={<Materials />} />
        <Route path="/service/reports" element={<ServiceReports />} />

        <Route path="/hr" element={<HrHome user={user} />} />
        <Route path="/hr/leave" element={<PermissionRoute user={user} permission="hr.leave.self"><HrLeave user={user} /></PermissionRoute>} />
        <Route path="/hr/approvals" element={<PermissionRoute user={user} permission="hr.leave.approve"><HrApprovals /></PermissionRoute>} />
        <Route path="/hr/summary" element={<PermissionRoute user={user} permission="hr.summary.view"><HrSummary /></PermissionRoute>} />
        <Route path="/hr/admin" element={<PermissionRoute user={user} permission="hr.admin"><HrAdmin /></PermissionRoute>} />
        <Route path="/hr/reports" element={<PermissionRoute user={user} permission="hr.summary.view"><HrReports /></PermissionRoute>} />
        <Route path="/crm" element={<CrmHome />} />
        <Route path="/crm/customers" element={<CrmCustomers user={user} />} />
        <Route path="/crm/customers/:customerId" element={<CrmCustomerDetail user={user} />} />
        <Route path="/crm/opportunities" element={<CrmOpportunities user={user} />} />
        <Route path="/crm/activities" element={<CrmActivities user={user} />} />
        <Route path="/crm/contracts" element={<CrmContracts user={user} />} />
        <Route path="/crm/reports" element={<CrmReports />} />

        <Route path="/procurement" element={<ProcurementRequests />} />
        <Route path="/procurement/new" element={<ProcurementNew />} />
        <Route path="/procurement/requests/:requestId" element={<ProcurementDetail user={user} />} />
        <Route path="/procurement/approvals" element={<PermissionRoute user={user} permission="procurement.approve" fallback="/procurement"><ProcurementApprovals /></PermissionRoute>} />

        <Route path="/notifications" element={<Notifications />} />

        <Route path="/admin" element={<AdminIndex user={user} />} />
        <Route path="/admin/backups" element={<PermissionRoute user={user} permission="admin.backup.manage" fallback="/modules"><Backups user={user} /></PermissionRoute>} />
        <Route path="/admin/users" element={<AdminRoleRoute user={user}><Users user={user} /></AdminRoleRoute>} />
        <Route path="/admin/settings" element={<AdminRoleRoute user={user}><Settings user={user} appInfo={appInfo} /></AdminRoleRoute>} />
        <Route path="/admin/audit" element={<AdminRoleRoute user={user}><AuditLogs /></AdminRoleRoute>} />

        <Route path="/work-orders/*" element={<LegacyServiceRedirect />} />
        <Route path="/work-order-archives" element={<LegacyServiceRedirect />} />
        <Route path="/assets/*" element={<LegacyServiceRedirect />} />
        <Route path="/customers" element={<LegacyServiceRedirect />} />
        <Route path="/materials" element={<LegacyServiceRedirect />} />
        <Route path="/users" element={<LegacyAdminRedirect />} />
        <Route path="/settings" element={<LegacyAdminRedirect />} />

        <Route path="*" element={<Navigate to="/modules" replace />} />
      </Routes>
    </Layout>
  )
}
