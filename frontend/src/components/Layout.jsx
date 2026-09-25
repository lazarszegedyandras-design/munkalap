import React, { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { hasPermission, moduleLabel } from '../utils/permissions.js'
import { api } from '../api.js'

const moduleItems = {
  service: [
    ['/service', 'Dashboard'],
    ['/service/work-orders', 'Munkalapok'],
    ['/service/assets', 'Eszközök'],
    ['/service/customers', 'Ügyfelek'],
    ['/service/materials', 'Anyagok'],
    ['/service/reports', 'Riportok'],
  ],
  hr: [
    ['/hr', 'HR áttekintés', null],
    ['/hr/leave', 'Saját szabadság', 'hr.leave.self'],
    ['/hr/approvals', 'Jóváhagyások', 'hr.leave.approve'],
    ['/hr/summary', 'Összesítés', 'hr.summary.view'],
    ['/hr/reports', 'Riportok', 'hr.summary.view'],
    ['/hr/admin', 'HR admin', 'hr.admin'],
  ],
  crm: [
    ['/crm', 'CRM áttekintés'],
    ['/crm/customers', 'Ügyfelek'],
    ['/crm/opportunities', 'Lehetőségek'],
    ['/crm/activities', 'Aktivitások'],
    ['/crm/contracts', 'Szerződések'],
    ['/crm/reports', 'Riportok'],
  ],
  procurement: [
    ['/procurement', 'Beszerzési igényeim'],
    ['/procurement/new', 'Új beszerzési igény'],
    ['/procurement/approvals', 'Jóváhagyások', 'procurement.approve'],
  ],
  admin: [
    ['/admin/backups', 'Biztonsági mentések', 'admin.backup.manage'],
    ['/admin/users', 'Felhasználók'],
    ['/admin/settings', 'Beállítások'],
    ['/admin/audit', 'Auditnapló'],
  ],
}

export default function Layout({ user, onLogout, appInfo, currentModule, children }) {
  const [unread, setUnread] = useState(0)
  async function refreshNotifications() { try { const r = await api('/notifications/unread-count'); setUnread(r.unread_count || 0) } catch {} }
  useEffect(() => { refreshNotifications(); const handler = () => refreshNotifications(); window.addEventListener('app:notifications-changed', handler); return () => window.removeEventListener('app:notifications-changed', handler) }, [])
  const adminOnlyPaths = new Set(['/admin/users', '/admin/settings', '/admin/audit'])
  const items = (moduleItems[currentModule] || []).filter(([to, , permission]) =>
    (!permission || hasPermission(user, permission)) && (!adminOnlyPaths.has(to) || user?.role?.name === 'Admin')
  )
  return (
    <div className="shell">
      <aside className="sidebar no-print">
        <div className="brand">Munkalap rendszer</div>
        <div className="app-version" title="Alkalmazásverzió">{appInfo?.version ? `v${appInfo.version}` : 'v–'}</div>
        {currentModule && <div className="module-badge">{moduleLabel(currentModule)} modul</div>}
        <nav>
          {items.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/service' || to === '/hr' || to === '/crm' || to === '/procurement'}>{label}</NavLink>
          ))}
        </nav>
        <div className="profile">
          <NavLink className="profile-action notification-link" to="/notifications">Értesítések {unread > 0 && <span className="notification-badge">{unread}</span>}</NavLink>
          <div>{user?.full_name}</div>
          <small>{user?.role?.name}</small>
          <NavLink className="profile-action module-switch" to="/modules">Modulválasztó</NavLink>
          <NavLink className="profile-action" to="/change-password">Jelszó módosítása</NavLink>
          <button onClick={onLogout}>Kilépés</button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}
