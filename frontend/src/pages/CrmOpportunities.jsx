import React, { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, downloadFile } from '../api.js'
import { Field } from '../components/FormField.jsx'
import { hasPermission } from '../utils/permissions.js'

const stages = ['új', 'kapcsolatfelvétel', 'igényfelmérés', 'ajánlat', 'tárgyalás', 'nyert', 'elvesztett']
const blank = { customer_id: '', contact_id: '', owner_user_id: '', title: '', stage: 'új', estimated_value: '', currency: 'HUF', probability: '', expected_close_date: '', source: '', next_step: '', lost_reason: '' }
const money = (value, currency='HUF') => value === null || value === undefined || value === '' ? '' : `${new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(value))} ${currency}`

export default function CrmOpportunities({ user }) {
  const [params, setParams] = useSearchParams()
  const [rows, setRows] = useState([])
  const [customers, setCustomers] = useState([])
  const [users, setUsers] = useState([])
  const [contacts, setContacts] = useState([])
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')
  const canWrite = hasPermission(user, 'crm.write')

  async function load() {
    try {
      const customerId = params.get('customer')
      const query = customerId ? `?customer_id=${customerId}` : ''
      const [opps, customerRows, crmUsers] = await Promise.all([api(`/crm/opportunities${query}`), api('/crm/customers'), api('/crm/users')])
      setRows(opps); setCustomers(customerRows); setUsers(crmUsers); setError('')
      const editId = Number(params.get('edit') || 0)
      if (editId && canWrite) {
        const row = opps.find(item => item.id === editId) || (await api('/crm/opportunities')).find(item => item.id === editId)
        if (row) startEdit(row)
      }
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [params.get('customer')])

  async function loadContacts(customerId) {
    if (!customerId) { setContacts([]); return }
    try { const detail = await api(`/crm/customers/${customerId}`); setContacts(detail.customer.contacts || []) } catch { setContacts([]) }
  }
  function startNew() {
    const customer = params.get('customer') || ''
    const next = { ...blank, customer_id: customer }
    setForm(next); loadContacts(customer)
  }
  function startEdit(row) {
    const next = { ...blank, ...row, customer_id: String(row.customer_id), contact_id: row.contact_id ? String(row.contact_id) : '', owner_user_id: row.owner_user_id ? String(row.owner_user_id) : '', estimated_value: row.estimated_value ?? '', probability: row.probability ?? '', expected_close_date: row.expected_close_date || '' }
    setForm(next); loadContacts(row.customer_id)
  }
  async function save(e) {
    e.preventDefault()
    const body = {
      customer_id: Number(form.customer_id), contact_id: form.contact_id ? Number(form.contact_id) : null, owner_user_id: form.owner_user_id ? Number(form.owner_user_id) : null,
      title: form.title, stage: form.stage, estimated_value: form.estimated_value === '' ? null : Number(form.estimated_value), currency: form.currency || 'HUF', probability: form.probability === '' ? null : Number(form.probability), expected_close_date: form.expected_close_date || null, source: form.source || null, next_step: form.next_step || null, lost_reason: form.lost_reason || null,
    }
    if (form.id) body.version = form.version
    try { await api(form.id ? `/crm/opportunities/${form.id}` : '/crm/opportunities', { method: form.id ? 'PUT' : 'POST', body }); setForm(null); params.delete('edit'); setParams(params, { replace: true }); await load() } catch (err) { setError(err.message) }
  }
  const grouped = useMemo(() => Object.fromEntries(stages.map(stage => [stage, rows.filter(row => row.stage === stage)])), [rows])

  return <section>
    <div className="page-head"><div><h1>Értékesítési lehetőségek</h1><p className="muted">Pipeline a közös ügyféltörzsre építve.</p></div><div className="inline-actions"><button className="secondary" onClick={()=>downloadFile(`/reports/crm-opportunities.csv${params.get('customer') ? `?customer_id=${params.get('customer')}` : ''}`)}>CSV export</button>{canWrite && <button onClick={startNew}>Új lehetőség</button>}</div></div>
    {error && <div className="error">{error}</div>}
    {form && <div className="panel"><h2>{form.id ? 'Lehetőség szerkesztése' : 'Új lehetőség'}</h2><form className="grid-form" onSubmit={save}>
      <Field label="Ügyfél"><select required value={form.customer_id} onChange={e => { setForm(p => ({...p,customer_id:e.target.value,contact_id:''})); loadContacts(e.target.value) }}><option value="">Válassz...</option>{customers.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></Field>
      <Field label="Kapcsolattartó"><select value={form.contact_id} onChange={e => setForm(p => ({...p,contact_id:e.target.value}))}><option value="">Nincs megadva</option>{contacts.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></Field>
      <Field label="Lehetőség neve"><input required value={form.title} onChange={e => setForm(p => ({...p,title:e.target.value}))} /></Field><Field label="Pipeline szakasz"><select value={form.stage} onChange={e => setForm(p => ({...p,stage:e.target.value}))}>{stages.map(stage => <option key={stage}>{stage}</option>)}</select></Field>
      <Field label="Várható érték"><input type="number" min="0" step="0.01" value={form.estimated_value} onChange={e => setForm(p => ({...p,estimated_value:e.target.value}))} /></Field><Field label="Deviza"><input maxLength="3" value={form.currency} onChange={e => setForm(p => ({...p,currency:e.target.value.toUpperCase()}))} /></Field>
      <Field label="Valószínűség %"><input type="number" min="0" max="100" value={form.probability} onChange={e => setForm(p => ({...p,probability:e.target.value}))} /></Field><Field label="Várható zárás"><input type="date" value={form.expected_close_date} onChange={e => setForm(p => ({...p,expected_close_date:e.target.value}))} /></Field>
      <Field label="CRM felelős"><select value={form.owner_user_id} onChange={e => setForm(p => ({...p,owner_user_id:e.target.value}))}><option value="">Saját magam / alapérték</option>{users.map(row => <option value={row.id} key={row.id}>{row.full_name}</option>)}</select></Field><Field label="Forrás"><input value={form.source || ''} onChange={e => setForm(p => ({...p,source:e.target.value}))} /></Field>
      <Field label="Következő lépés"><textarea value={form.next_step || ''} onChange={e => setForm(p => ({...p,next_step:e.target.value}))} /></Field><Field label="Elvesztés oka"><textarea value={form.lost_reason || ''} onChange={e => setForm(p => ({...p,lost_reason:e.target.value}))} /></Field>
      <div className="form-actions"><button>Mentés</button><button type="button" className="secondary" onClick={() => setForm(null)}>Mégse</button></div>
    </form></div>}
    <div className="crm-pipeline">{stages.map(stage => <div className="crm-pipeline-column" key={stage}><h2>{stage} <span>{grouped[stage].length}</span></h2>{grouped[stage].map(row => <button disabled={!canWrite} className="crm-opportunity-card" key={row.id} onClick={() => canWrite && startEdit(row)}><strong>{row.title}</strong><span>{row.customer_name}</span><small>{money(row.estimated_value, row.currency)}{row.probability !== null ? ` · ${row.probability}%` : ''}</small><small>{row.owner_name || ''}</small></button>)}</div>)}</div>
  </section>
}
