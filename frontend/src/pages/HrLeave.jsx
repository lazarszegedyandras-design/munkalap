import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'
import { Field } from '../components/FormField.jsx'
import { hasPermission } from '../utils/permissions.js'

const statusLabel = { pending: 'Jóváhagyásra vár', approved: 'Jóváhagyva', rejected: 'Elutasítva', cancelled: 'Visszavonva' }
const leaveTypeLabel = { annual_leave: 'Szabadság', sick_leave: 'Betegszabadság' }
const currentYear = new Date().getFullYear()

function displayStatus(row) {
  if (row.cancellation_status === 'pending') return 'Visszavonás jóváhagyásra vár'
  if (row.cancellation_status === 'rejected') return 'Jóváhagyva · visszavonás elutasítva'
  if (row.status === 'cancelled' && row.cancellation_status === 'approved') return 'Visszavonva · jóváhagyva'
  return statusLabel[row.status] || row.status
}

export default function HrLeave({ user }) {
  const [year, setYear] = useState(currentYear)
  const [data, setData] = useState(null)
  const [form, setForm] = useState({ start_date: '', end_date: '', employee_comment: '' })
  const [cancellationForm, setCancellationForm] = useState(null)
  const [error, setError] = useState('')
  const canRequest = hasPermission(user, 'hr.leave.request')

  useEffect(() => { load() }, [year])
  async function load() { setError(''); try { setData(await api(`/hr/me?year=${year}`)) } catch (err) { setError(err.message) } }
  async function submit(e) {
    e.preventDefault(); setError('')
    try {
      await api('/hr/me/leave-requests', { method: 'POST', body: form })
      setForm({ start_date: '', end_date: '', employee_comment: '' })
      await load()
    } catch (err) { setError(err.message) }
  }
  async function cancel(row) {
    if (!confirm('Biztosan visszavonod ezt a még el nem bírált szabadságigényt?')) return
    try { await api(`/hr/me/leave-requests/${row.id}/cancel`, { method: 'POST', body: { version: row.version } }); await load() }
    catch (err) { setError(err.message) }
  }
  async function requestCancellation(e) {
    e.preventDefault(); setError('')
    try {
      await api(`/hr/me/leave-requests/${cancellationForm.id}/request-cancellation`, {
        method: 'POST',
        body: { version: cancellationForm.version, comment: cancellationForm.comment || null },
      })
      setCancellationForm(null)
      await load()
    } catch (err) { setError(err.message) }
  }

  const b = data?.balance
  return <section>
    <div className="page-head"><div><h1>Saját szabadság</h1><p className="muted">Csak a saját HR szabadság- és betegszabadságadataid jelennek meg ezen az oldalon.</p></div>
      <Field label="Év"><select value={year} onChange={e => setYear(Number(e.target.value))}>{[currentYear-1,currentYear,currentYear+1].map(y => <option key={y}>{y}</option>)}</select></Field>
    </div>
    {error && <div className="error">{error}</div>}
    {b && <div className="hr-stat-grid">
      <div className="hr-stat"><span>Éves szabadságkeret</span><strong>{b.total_days} nap</strong><small>Alap {b.base_days} · Gyermek után {b.child_days} · Áthozott {b.carried_days} · Korrekció {b.adjustment_days}</small></div>
      <div className="hr-stat"><span>Kiadott / jóváhagyott</span><strong>{b.approved_days} nap</strong></div>
      <div className="hr-stat"><span>Függőben</span><strong>{b.pending_days} nap</strong></div>
      <div className="hr-stat"><span>Igényelhető</span><strong>{b.available_to_request_days} nap</strong><small>Jóváhagyott utáni maradék: {b.remaining_days}</small></div>
      <div className="hr-stat"><span>Betegszabadság</span><strong>{b.sick_leave_used_days} / {b.sick_leave_entitlement_days} nap</strong><small>Maradék: {b.sick_leave_remaining_days} nap</small></div>
    </div>}

    {canRequest && <div className="panel">
      <h2>Új szabadságigény</h2>
      <form className="grid-form" onSubmit={submit}>
        <Field label="Kezdőnap"><input type="date" required value={form.start_date} onChange={e => setForm(p => ({...p,start_date:e.target.value}))} /></Field>
        <Field label="Zárónap"><input type="date" required value={form.end_date} onChange={e => setForm(p => ({...p,end_date:e.target.value}))} /></Field>
        <Field label="Megjegyzés"><textarea value={form.employee_comment} onChange={e => setForm(p => ({...p,employee_comment:e.target.value}))} /></Field>
        <div className="form-actions"><button>Igény beküldése</button></div>
      </form>
      <p className="muted">A munkanapok számítása hétfő–péntek alapján történik, a HR admin által rögzített munkanaptár-kivételekkel korrigálva.</p>
    </div>}

    <div className="panel"><h2>Saját igények és előzmények</h2>
      <DataTable rows={data?.leave_requests || []} columns={[
        {key:'leave_type',label:'Típus',render:r=>leaveTypeLabel[r.leave_type] || r.leave_type},
        {key:'start_date',label:'Kezdet'}, {key:'end_date',label:'Vége'}, {key:'requested_days',label:'Nap'},
        {key:'status',label:'Státusz',render:displayStatus},
        {key:'approver_name',label:'Jóváhagyó',render:r=>r.approver_name || ''},
        {key:'source',label:'Forrás',render:r=>r.source === 'rlb_pdf_2026' ? 'RLB 2026 nyilvántartás' : 'HR folyamat'},
        {key:'employee_comment',label:'Megjegyzés',render:r=>r.employee_comment || ''},
        {key:'approver_comment',label:'Vezetői megjegyzés',render:r=>r.cancellation_approver_comment || r.approver_comment || ''},
      ]} actions={row => {
        if (row.status === 'pending' && row.source === 'workflow') return <button className="danger" onClick={() => cancel(row)}>Függő igény visszavonása</button>
        if (row.status === 'approved' && row.cancellation_status !== 'pending') return <button className="danger" onClick={() => setCancellationForm({ id: row.id, version: row.version, start_date: row.start_date, end_date: row.end_date, comment: '' })}>Szabadság visszavonása</button>
        return null
      }} />
    </div>
    {cancellationForm && <div className="panel">
      <h2>Szabadság-visszavonás kérelmezése</h2>
      <p>A {cancellationForm.start_date} – {cancellationForm.end_date} közötti szabadság a jóváhagyó döntéséig érvényben marad.</p>
      <form className="grid-form one" onSubmit={requestCancellation}>
        <Field label="Visszavonás indoka"><textarea value={cancellationForm.comment} onChange={e => setCancellationForm(p => ({...p,comment:e.target.value}))} placeholder="Opcionális" /></Field>
        <div className="form-actions"><button>Kérelem beküldése</button><button type="button" className="secondary" onClick={() => setCancellationForm(null)}>Mégse</button></div>
      </form>
    </div>}
  </section>
}
