import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

const stageLabels = ['új', 'kapcsolatfelvétel', 'igényfelmérés', 'ajánlat', 'tárgyalás', 'nyert', 'elvesztett']
const money = (value) => new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(value || 0)) + ' Ft'

export default function CrmHome() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api('/crm/dashboard').then(setData).catch(err => setError(err.message)) }, [])

  return <section>
    <div className="page-head"><div><h1>CRM</h1><p className="muted">Közös ügyféltörzs, értékesítési pipeline és ügyfélaktivitások.</p></div></div>
    {error && <div className="error">{error}</div>}
    {data && <>
      <div className="crm-stat-grid">
        <div className="crm-stat"><span>Ügyfelek</span><strong>{data.customer_count}</strong></div>
        <div className="crm-stat"><span>Nyitott lehetőségek</span><strong>{data.open_opportunity_count}</strong></div>
        <div className="crm-stat"><span>Nyitott pipeline</span><strong>{money(data.open_pipeline_value)}</strong></div>
        <div className="crm-stat"><span>Lejárt feladatok</span><strong>{data.overdue_activity_count}</strong></div>
        <div className="crm-stat"><span>Aktív szerződések</span><strong>{data.active_contract_count}</strong></div>
        <div className="crm-stat"><span>60 napon belül lejár</span><strong>{data.expiring_contract_count}</strong></div>
      </div>
      <div className="crm-shortcuts">
        <Link to="/crm/customers">Ügyféltörzs és 360° nézet</Link>
        <Link to="/crm/opportunities">Értékesítési lehetőségek</Link>
        <Link to="/crm/activities">Aktivitások és feladatok</Link>
        <Link to="/crm/contracts">Szerződések</Link>
        <Link to="/crm/reports">CRM riportok és export</Link>
      </div>
      <div className="panel"><h2>Pipeline szakaszok</h2><div className="crm-stage-grid">
        {stageLabels.map(stage => <div key={stage} className="crm-stage-stat"><span>{stage}</span><strong>{data.opportunities_by_stage?.[stage] || 0}</strong></div>)}
      </div></div>
      <div className="crm-two-col">
        <div className="panel"><h2>Legutóbbi lehetőségek</h2>{data.recent_opportunities?.length ? <div className="crm-feed">{data.recent_opportunities.map(row => <Link to={`/crm/opportunities?edit=${row.id}`} key={row.id}><strong>{row.title}</strong><span>{row.customer_name} · {row.stage}</span></Link>)}</div> : <p className="muted">Nincs még lehetőség.</p>}</div>
        <div className="panel"><h2>Legutóbbi aktivitások</h2>{data.recent_activities?.length ? <div className="crm-feed">{data.recent_activities.map(row => <Link to={`/crm/activities?customer=${row.customer_id}`} key={row.id}><strong>{row.subject}</strong><span>{row.customer_name} · {row.activity_type}</span></Link>)}</div> : <p className="muted">Nincs még aktivitás.</p>}</div>
      </div>
    </>}
  </section>
}
