import React from 'react'
import { Link } from 'react-router-dom'
import { hasPermission } from '../utils/permissions.js'

export default function HrHome({ user }) {
  const items = [
    ['hr.leave.self', '/hr/leave', 'Saját szabadság', 'Éves keret, saját igények és új szabadságigény.'],
    ['hr.leave.approve', '/hr/approvals', 'Jóváhagyások', 'A hozzád rendelt szabadságigények vezetői döntése.'],
    ['hr.summary.view', '/hr/summary', 'HR összesítés', 'Munkavállalónkénti éves szabadság-összesítés.'],
    ['hr.summary.view', '/hr/reports', 'HR riportok', 'Szervezeti és havi aggregált szabadságriportok, CSV exporttal.'],
    ['hr.admin', '/hr/admin', 'HR adminisztráció', 'Munkavállalói profilok, éves keretek és munkanaptár.'],
  ].filter(([permission]) => hasPermission(user, permission))

  return <section>
    <div className="page-head"><div><h1>HR</h1><p className="muted">Szabadságkezelés és vezetői jóváhagyás.</p></div></div>
    {items.length ? <div className="hr-feature-grid">
      {items.map(([permission, to, title, description]) => <Link className="hr-feature-card" to={to} key={permission}>
        <strong>{title}</strong><span>{description}</span>
      </Link>)}
    </div> : <div className="panel">A HR modulhoz van hozzáférésed, de részletes HR funkciójogosultság nincs hozzárendelve.</div>}
  </section>
}
