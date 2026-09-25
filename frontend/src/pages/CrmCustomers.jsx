import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Field } from '../components/FormField.jsx'
import { hasPermission } from '../utils/permissions.js'

const emptyForm = { name: '', company_code: '', contact_person: '', phone: '', email: '', address: '', note: '' }
const money = (value) => new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(value || 0)) + ' Ft'

export default function CrmCustomers({ user }) {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')
  const canWrite = hasPermission(user, 'crm.write')

  async function load(search = q) { try { setRows(await api(`/crm/customers${search ? `?q=${encodeURIComponent(search)}` : ''}`)); setError('') } catch (err) { setError(err.message) } }
  useEffect(() => { load('') }, [])
  async function submit(e) {
    e.preventDefault()
    try { await api('/crm/customers', { method: 'POST', body: form }); setForm(emptyForm); setShowForm(false); await load() } catch (err) { setError(err.message) }
  }

  return <section>
    <div className="page-head"><div><h1>CRM ügyfelek</h1><p className="muted">A Szerviz modullal közös ügyféltörzs. Nincs külön CRM ügyfélmásolat.</p></div>{canWrite && <button onClick={() => setShowForm(v => !v)}>{showForm ? 'Mégse' : 'Új ügyfél'}</button>}</div>
    {error && <div className="error">{error}</div>}
    <div className="panel crm-search"><Field label="Keresés"><input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') load() }} placeholder="Cégnév, cégkód, e-mail" /></Field><button onClick={() => load()}>Keresés</button></div>
    {showForm && <div className="panel"><h2>Új ügyfél</h2><form className="grid-form" onSubmit={submit}>
      <Field label="Cégnév"><input required value={form.name} onChange={e => setForm(p => ({...p,name:e.target.value}))} /></Field>
      <Field label="Cégkód"><input value={form.company_code} onChange={e => setForm(p => ({...p,company_code:e.target.value}))} /></Field>
      <Field label="Kapcsolattartó"><input value={form.contact_person} onChange={e => setForm(p => ({...p,contact_person:e.target.value}))} /></Field>
      <Field label="Telefon"><input value={form.phone} onChange={e => setForm(p => ({...p,phone:e.target.value}))} /></Field>
      <Field label="E-mail"><input type="email" value={form.email} onChange={e => setForm(p => ({...p,email:e.target.value}))} /></Field>
      <Field label="Cím"><input value={form.address} onChange={e => setForm(p => ({...p,address:e.target.value}))} /></Field>
      <Field label="Megjegyzés"><textarea value={form.note} onChange={e => setForm(p => ({...p,note:e.target.value}))} /></Field>
      <div className="form-actions"><button>Mentés</button></div>
    </form></div>}
    <div className="panel"><div className="table-wrap"><table><thead><tr><th>Ügyfél</th><th>Kapcsolatok</th><th>Helyszínek</th><th>Eszközök</th><th>Munkalapok</th><th>Nyitott lehetőség</th><th>Pipeline</th></tr></thead><tbody>
      {rows.map(row => <tr key={row.id}><td><Link to={`/crm/customers/${row.id}`}><strong>{row.name}</strong></Link><br/><small>{row.company_code || ''}</small></td><td>{row.contact_count}</td><td>{row.location_count}</td><td>{row.asset_count}</td><td>{row.work_order_count}</td><td>{row.open_opportunity_count}</td><td>{money(row.open_pipeline_value)}</td></tr>)}
      {!rows.length && <tr><td colSpan="7" className="muted">Nincs találat.</td></tr>}
    </tbody></table></div></div>
  </section>
}
