import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'

export default function HrApprovals() {
  const [rows, setRows] = useState([])
  const [comments, setComments] = useState({})
  const [error, setError] = useState('')
  useEffect(() => { load() }, [])
  async function load() { try { setRows(await api('/hr/approvals?status=pending')); setError('') } catch (err) { setError(err.message) } }
  async function decide(row, decision) {
    try {
      const path = row.approval_kind === 'cancellation'
        ? `/hr/approvals/${row.id}/cancellation/${decision}`
        : `/hr/approvals/${row.id}/${decision}`
      await api(path, { method: 'POST', body: { version: row.version, comment: comments[row.id] || '' } })
      await load()
    } catch (err) { setError(err.message) }
  }
  return <section>
    <div className="page-head"><div><h1>Szabadság jóváhagyások</h1><p className="muted">A hozzád rendelt új szabadságigények és visszavonási kérelmek jelennek meg.</p></div></div>
    {error && <div className="error">{error}</div>}
    <DataTable rows={rows} columns={[
      {key:'employee_name',label:'Munkavállaló'}, {key:'approval_kind',label:'Döntés tárgya',render:r=>r.approval_kind === 'cancellation' ? 'Szabadság visszavonása' : 'Új szabadságigény'}, {key:'start_date',label:'Kezdet'}, {key:'end_date',label:'Vége'},
      {key:'requested_days',label:'Nap'}, {key:'employee_comment',label:'Munkavállalói megjegyzés',render:r=>r.approval_kind === 'cancellation' ? (r.cancellation_comment || '') : (r.employee_comment || '')},
      {key:'decision_comment',label:'Vezetői megjegyzés',sortable:false,render:r=><input className="hr-inline-comment" value={comments[r.id] || ''} onChange={e=>setComments(p=>({...p,[r.id]:e.target.value}))} />},
    ]} actions={row => <><button onClick={() => decide(row,'approve')}>{row.approval_kind === 'cancellation' ? 'Visszavonás engedélyezése' : 'Jóváhagyás'}</button><button className="danger" onClick={() => decide(row,'reject')}>{row.approval_kind === 'cancellation' ? 'Visszavonás elutasítása' : 'Elutasítás'}</button></>} />
    {!rows.length && <div className="panel muted">Nincs jóváhagyásra váró szabadságigény vagy visszavonás.</div>}
  </section>
}
