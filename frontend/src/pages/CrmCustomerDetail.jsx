import React, { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { Field } from '../components/FormField.jsx'
import { hasPermission } from '../utils/permissions.js'

const blankContact = { category: 'Sales', name: '', title: '', phone: '', email: '', location_id: '', note: '', is_primary: false }

export default function CrmCustomerDetail({ user }) {
  const { customerId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [editingCustomer, setEditingCustomer] = useState(false)
  const [customerForm, setCustomerForm] = useState({})
  const [contactForm, setContactForm] = useState(null)
  const canWrite = hasPermission(user, 'crm.write')

  async function load() { try { const next = await api(`/crm/customers/${customerId}`); setData(next); setError(''); setCustomerForm(next.customer) } catch (err) { setError(err.message) } }
  useEffect(() => { load() }, [customerId])
  const locations = data?.customer?.locations || []
  const selectableLocations = locations.filter(row => row.is_active !== false || (contactForm?.id && row.id === Number(contactForm.location_id)))
  const contacts = data?.customer?.contacts || []
  const contactInitial = useMemo(() => blankContact, [])

  async function saveCustomer(e) {
    e.preventDefault()
    try {
      const body = { name: customerForm.name, company_code: customerForm.company_code || null, contact_person: customerForm.contact_person || null, phone: customerForm.phone || null, email: customerForm.email || null, address: customerForm.address || null, note: customerForm.note || null }
      await api(`/crm/customers/${customerId}`, { method: 'PUT', body }); setEditingCustomer(false); await load()
    } catch (err) { setError(err.message) }
  }
  function startContact(contact = null) {
    setContactForm(contact ? { ...contact, location_id: contact.location_id || '' } : { ...contactInitial })
  }
  async function saveContact(e) {
    e.preventDefault()
    const existingId = contactForm.id
    const body = { ...contactForm, location_id: contactForm.location_id ? Number(contactForm.location_id) : null }
    delete body.id; delete body.customer_id; delete body.location_name; delete body.created_at
    try {
      await api(existingId ? `/crm/customers/${customerId}/contacts/${existingId}` : `/crm/customers/${customerId}/contacts`, { method: existingId ? 'PUT' : 'POST', body })
      setContactForm(null); await load()
    } catch (err) { setError(err.message) }
  }

  if (!data) return <section><h1>CRM ügyfél</h1>{error ? <div className="error">{error}</div> : <p>Betöltés...</p>}</section>
  const c = data.customer
  return <section>
    <div className="page-head"><div><h1>{c.name}</h1><p className="muted">CRM 360° ügyfélnézet · ugyanaz az ügyféladat, amelyet a Szerviz modul használ.</p></div><div className="inline-actions"><Link className="button secondary" to={`/crm/opportunities?customer=${c.id}`}>Lehetőségek</Link><Link className="button secondary" to={`/crm/activities?customer=${c.id}`}>Aktivitások</Link><Link className="button secondary" to={`/crm/contracts?customer=${c.id}`}>Szerződések</Link>{canWrite && <button onClick={() => setEditingCustomer(v => !v)}>{editingCustomer ? 'Mégse' : 'Ügyfél szerkesztése'}</button>}</div></div>
    {error && <div className="error">{error}</div>}
    <div className="crm-stat-grid">
      <div className="crm-stat"><span>Kapcsolattartók</span><strong>{data.summary.contact_count}</strong></div><div className="crm-stat"><span>Eszközök</span><strong>{data.summary.asset_count}</strong></div><div className="crm-stat"><span>Munkalapok</span><strong>{data.summary.work_order_count}</strong></div><div className="crm-stat"><span>Nyitott lehetőség</span><strong>{data.summary.open_opportunity_count}</strong></div>
    </div>
    {editingCustomer && <div className="panel"><h2>Ügyféladatok módosítása</h2><form className="grid-form" onSubmit={saveCustomer}>
      <Field label="Cégnév"><input required value={customerForm.name || ''} onChange={e => setCustomerForm(p => ({...p,name:e.target.value}))} /></Field><Field label="Cégkód"><input value={customerForm.company_code || ''} onChange={e => setCustomerForm(p => ({...p,company_code:e.target.value}))} /></Field><Field label="Kapcsolattartó"><input value={customerForm.contact_person || ''} onChange={e => setCustomerForm(p => ({...p,contact_person:e.target.value}))} /></Field><Field label="Telefon"><input value={customerForm.phone || ''} onChange={e => setCustomerForm(p => ({...p,phone:e.target.value}))} /></Field><Field label="E-mail"><input type="email" value={customerForm.email || ''} onChange={e => setCustomerForm(p => ({...p,email:e.target.value}))} /></Field><Field label="Cím"><input value={customerForm.address || ''} onChange={e => setCustomerForm(p => ({...p,address:e.target.value}))} /></Field><Field label="Megjegyzés"><textarea value={customerForm.note || ''} onChange={e => setCustomerForm(p => ({...p,note:e.target.value}))} /></Field><div className="form-actions"><button>Mentés</button></div>
    </form></div>}
    <div className="crm-two-col">
      <div className="panel"><div className="crm-contact-head"><h2>Kapcsolattartók</h2>{canWrite && <button className="secondary" onClick={() => startContact()}>Új kapcsolattartó</button>}</div>
        {contacts.length ? contacts.map(row => <div className="crm-contact-card" key={row.id}><div><strong>{row.name}</strong> <span className="muted">{row.category}</span>{row.is_primary && <span className="status ok">Elsődleges</span>}<br/><small>{row.title || ''} {row.location_name ? `· ${row.location_name}` : ''}</small><br/><span>{[row.phone,row.email].filter(Boolean).join(' · ')}</span></div>{canWrite && <button className="secondary" onClick={() => startContact(row)}>Szerkesztés</button>}</div>) : <p className="muted">Nincs kapcsolattartó.</p>}
      </div>
      <div className="panel"><h2>Telephelyek</h2>{locations.length ? <ul>{locations.map(row => <li key={row.id}><strong>{row.name}</strong>{row.address ? ` — ${row.address}` : ''}{row.is_active === false ? ' · inaktív' : ''}</li>)}</ul> : <p className="muted">Nincs telephely.</p>}</div>
    </div>
    {contactForm && <div className="panel"><h2>{contactForm.id ? 'Kapcsolattartó szerkesztése' : 'Új kapcsolattartó'}</h2><form className="grid-form" onSubmit={saveContact}>
      <Field label="Név"><input required value={contactForm.name} onChange={e => setContactForm(p => ({...p,name:e.target.value}))} /></Field><Field label="Kategória"><select value={contactForm.category} onChange={e => setContactForm(p => ({...p,category:e.target.value}))}><option>Sales</option><option>Szerviz</option><option>Egyéb</option></select></Field><Field label="Beosztás"><input value={contactForm.title || ''} onChange={e => setContactForm(p => ({...p,title:e.target.value}))} /></Field><Field label="Helyszín"><select value={contactForm.location_id || ''} onChange={e => setContactForm(p => ({...p,location_id:e.target.value}))}><option value="">Általános</option>{selectableLocations.map(row => <option value={row.id} key={row.id}>{row.name}{row.is_active === false ? ' · inaktív (meglévő)' : ''}</option>)}</select></Field><Field label="Telefon"><input value={contactForm.phone || ''} onChange={e => setContactForm(p => ({...p,phone:e.target.value}))} /></Field><Field label="E-mail"><input type="email" value={contactForm.email || ''} onChange={e => setContactForm(p => ({...p,email:e.target.value}))} /></Field><Field label="Megjegyzés"><textarea value={contactForm.note || ''} onChange={e => setContactForm(p => ({...p,note:e.target.value}))} /></Field><label className="checkbox"><input type="checkbox" checked={!!contactForm.is_primary} onChange={e => setContactForm(p => ({...p,is_primary:e.target.checked}))} /> Elsődleges kapcsolattartó</label><div className="form-actions"><button>Mentés</button><button type="button" className="secondary" onClick={() => setContactForm(null)}>Mégse</button></div>
    </form></div>}
    <div className="panel"><h2>Értékesítési lehetőségek</h2>{data.opportunities.length ? <div className="crm-feed">{data.opportunities.map(row => <Link to={`/crm/opportunities?edit=${row.id}`} key={row.id}><strong>{row.title}</strong><span>{row.stage}{row.estimated_value ? ` · ${row.estimated_value} ${row.currency}` : ''}</span></Link>)}</div> : <p className="muted">Nincs lehetőség.</p>}</div>
    <div className="panel"><h2>Szerződések</h2>{data.contracts?.length ? <div className="crm-feed">{data.contracts.map(row => <Link to={`/crm/contracts?customer=${c.id}`} key={row.id}><strong>{row.contract_number} · {row.contract_type}</strong><span>{row.status}{row.end_date ? ` · ${row.end_date}` : ''}</span></Link>)}</div> : <p className="muted">Nincs CRM szerződés.</p>}</div>
    <div className="crm-two-col"><div className="panel"><h2>Eszközök</h2>{data.assets.length ? <div className="table-wrap"><table><thead><tr><th>Belső azonosító</th><th>Típus / modell</th><th>Gyári szám</th><th>Állapot</th></tr></thead><tbody>{data.assets.map(row => <tr key={row.id}><td>{row.internal_id}</td><td>{[row.type,row.model].filter(Boolean).join(' / ')}</td><td>{row.serial_number || ''}</td><td>{row.status}</td></tr>)}</tbody></table></div> : <p className="muted">Nincs eszköz.</p>}</div>
      <div className="panel"><h2>Legutóbbi munkalapok</h2>{data.work_orders.length ? <div className="crm-feed">{data.work_orders.map(row => <Link to={`/service/work-orders/${row.id}`} key={row.id}><strong>{row.number}</strong><span>{row.work_type || ''} · {row.status}</span></Link>)}</div> : <p className="muted">Nincs munkalap.</p>}</div></div>
    <div className="panel"><h2>Aktivitási idővonal</h2>{data.activities.length ? <div className="crm-activity-feed">{data.activities.map(row => <article key={row.id}><strong>{row.subject}</strong><span>{row.activity_type} · {row.owner_name || ''}</span><small>{row.description || ''}</small></article>)}</div> : <p className="muted">Nincs CRM aktivitás.</p>}</div>
  </section>
}
