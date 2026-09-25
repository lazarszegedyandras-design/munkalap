import React, { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, downloadFile } from '../api.js'
import { Field } from '../components/FormField.jsx'
import { hasPermission } from '../utils/permissions.js'

const types = ['telefon', 'e-mail', 'meeting', 'feladat', 'jegyzet']
const blank = { customer_id: '', contact_id: '', opportunity_id: '', work_order_id: '', owner_user_id: '', activity_type: 'telefon', subject: '', description: '', due_at: '', completed_at: '' }
const localInput = value => value ? String(value).slice(0, 16) : ''

export default function CrmActivities({ user }) {
  const [params] = useSearchParams()
  const [rows, setRows] = useState([])
  const [customers, setCustomers] = useState([])
  const [users, setUsers] = useState([])
  const [contacts, setContacts] = useState([])
  const [opportunities, setOpportunities] = useState([])
  const [workOrders, setWorkOrders] = useState([])
  const [form, setForm] = useState(null)
  const [convertingId, setConvertingId] = useState(null)
  const [error, setError] = useState('')
  const canWrite = hasPermission(user, 'crm.write')

  async function load() {
    try {
      const customerId = params.get('customer')
      const query = customerId ? `?customer_id=${customerId}` : ''
      const [activityRows, customerRows, crmUsers] = await Promise.all([api(`/crm/activities${query}`), api('/crm/customers'), api('/crm/users')])
      setRows(activityRows); setCustomers(customerRows); setUsers(crmUsers); setError('')
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [params.get('customer')])

  async function loadLinks(customerId) {
    if (!customerId) { setContacts([]); setOpportunities([]); setWorkOrders([]); return }
    try {
      const [detail, opps] = await Promise.all([api(`/crm/customers/${customerId}`), api(`/crm/opportunities?customer_id=${customerId}`)])
      setContacts(detail.customer.contacts || []); setWorkOrders(detail.work_orders || []); setOpportunities(opps)
    } catch { setContacts([]); setOpportunities([]); setWorkOrders([]) }
  }
  function startNew() {
    const customerId = params.get('customer') || ''
    setForm({ ...blank, customer_id: customerId }); loadLinks(customerId)
  }
  function startEdit(row) {
    setForm({ ...blank, ...row, customer_id: String(row.customer_id), contact_id: row.contact_id ? String(row.contact_id) : '', opportunity_id: row.opportunity_id ? String(row.opportunity_id) : '', work_order_id: row.work_order_id ? String(row.work_order_id) : '', owner_user_id: row.owner_user_id ? String(row.owner_user_id) : '', due_at: localInput(row.due_at), completed_at: localInput(row.completed_at) }); loadLinks(row.customer_id)
  }
  async function save(e) {
    e.preventDefault()
    const body = { customer_id: Number(form.customer_id), contact_id: form.contact_id ? Number(form.contact_id) : null, opportunity_id: form.opportunity_id ? Number(form.opportunity_id) : null, work_order_id: form.work_order_id ? Number(form.work_order_id) : null, owner_user_id: form.owner_user_id ? Number(form.owner_user_id) : null, activity_type: form.activity_type, subject: form.subject, description: form.description || null, due_at: form.due_at || null, completed_at: form.completed_at || null }
    if (form.id) body.version = form.version
    try { await api(form.id ? `/crm/activities/${form.id}` : '/crm/activities', { method: form.id ? 'PUT' : 'POST', body }); setForm(null); await load() } catch (err) { setError(err.message) }
  }
  async function complete(row) {
    try { await api(`/crm/activities/${row.id}`, { method: 'PUT', body: { version: row.version, completed_at: new Date().toISOString().slice(0, 19) } }); await load() } catch (err) { setError(err.message) }
  }
  async function createOpportunity(row) {
    setConvertingId(row.id); setError('')
    try { await api(`/crm/activities/${row.id}/opportunity`, { method: 'POST', body: { version: row.version } }); await load() }
    catch (err) { setError(err.message) }
    finally { setConvertingId(null) }
  }

  return <section>
    <div className="page-head"><div><h1>CRM aktivitások</h1><p className="muted">Telefonok, e-mailek, meetingek, feladatok és jegyzetek időrendben.</p></div><div className="inline-actions"><button className="secondary" onClick={()=>downloadFile(`/reports/crm-activities.csv${params.get('customer') ? `?customer_id=${params.get('customer')}` : ''}`)}>CSV export</button>{canWrite && <button onClick={startNew}>Új aktivitás</button>}</div></div>
    {error && <div className="error">{error}</div>}
    {form && <div className="panel"><h2>{form.id ? 'Aktivitás szerkesztése' : 'Új aktivitás'}</h2><form className="grid-form" onSubmit={save}>
      <Field label="Ügyfél"><select required value={form.customer_id} onChange={e => { setForm(p => ({...p,customer_id:e.target.value,contact_id:'',opportunity_id:'',work_order_id:''})); loadLinks(e.target.value) }}><option value="">Válassz...</option>{customers.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></Field>
      <Field label="Típus"><select value={form.activity_type} onChange={e => setForm(p => ({...p,activity_type:e.target.value}))}>{types.map(type => <option key={type}>{type}</option>)}</select></Field>
      <Field label="Tárgy"><input required value={form.subject} onChange={e => setForm(p => ({...p,subject:e.target.value}))} /></Field><Field label="Kapcsolattartó"><select value={form.contact_id} onChange={e => setForm(p => ({...p,contact_id:e.target.value}))}><option value="">Nincs</option>{contacts.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></Field>
      <Field label="Lehetőség"><select value={form.opportunity_id} onChange={e => setForm(p => ({...p,opportunity_id:e.target.value}))}><option value="">Nincs</option>{opportunities.map(row => <option value={row.id} key={row.id}>{row.title}</option>)}</select></Field><Field label="Munkalap"><select value={form.work_order_id} onChange={e => setForm(p => ({...p,work_order_id:e.target.value}))}><option value="">Nincs</option>{workOrders.map(row => <option value={row.id} key={row.id}>{row.number}</option>)}</select></Field>
      <Field label="Felelős"><select value={form.owner_user_id} onChange={e => setForm(p => ({...p,owner_user_id:e.target.value}))}><option value="">Saját magam / alapérték</option>{users.map(row => <option value={row.id} key={row.id}>{row.full_name}</option>)}</select></Field><Field label="Határidő"><input type="datetime-local" value={form.due_at} onChange={e => setForm(p => ({...p,due_at:e.target.value}))} /></Field>
      <Field label="Leírás"><textarea value={form.description || ''} onChange={e => setForm(p => ({...p,description:e.target.value}))} /></Field><Field label="Elvégezve"><input type="datetime-local" value={form.completed_at} onChange={e => setForm(p => ({...p,completed_at:e.target.value}))} /></Field>
      <div className="form-actions"><button>Mentés</button><button type="button" className="secondary" onClick={() => setForm(null)}>Mégse</button></div>
    </form></div>}
    <div className="panel"><div className="crm-activity-feed">{rows.map(row => <article key={row.id} className={row.completed_at ? 'completed' : ''}><div><strong>{row.subject}</strong><span>{row.customer_name} · {row.activity_type}{row.owner_name ? ` · ${row.owner_name}` : ''}</span><small>{row.description || ''}</small>{row.due_at && <small>Határidő: {new Date(row.due_at).toLocaleString('hu-HU')}</small>}{row.opportunity_title && <small>Lehetőség: <Link to={`/crm/opportunities?edit=${row.opportunity_id}`}>{row.opportunity_title}</Link></small>}{row.work_order_number && <small>Munkalap: {row.work_order_number}</small>}</div>{canWrite && <div className="inline-actions">{!row.opportunity_id && <button className="secondary" disabled={convertingId === row.id} onClick={() => createOpportunity(row)}>{convertingId === row.id ? 'Létrehozás…' : 'Lehetőség létrehozása'}</button>}<button className="secondary" onClick={() => startEdit(row)}>Szerkesztés</button>{!row.completed_at && <button onClick={() => complete(row)}>Kész</button>}</div>}</article>)}{!rows.length && <p className="muted">Nincs CRM aktivitás.</p>}</div></div>
  </section>
}
