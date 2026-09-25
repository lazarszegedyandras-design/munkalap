import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'
import { Field } from '../components/FormField.jsx'

const contactCategories = ['Szerviz', 'Sales', 'Egyéb']
const emptyCustomer = { name: '', company_code: '', contact_person: '', phone: '', email: '', address: '', note: '' }
const emptyLocation = { customer_id: '', name: '', address: '', gps_lat: '', gps_lng: '', note: '' }
const emptyContact = { customer_id: '', location_id: '', category: 'Szerviz', name: '', title: '', phone: '', email: '', note: '', is_primary: false }

export default function Customers({ user }) {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState([])
  const [customerForm, setCustomerForm] = useState(emptyCustomer)
  const [locationForm, setLocationForm] = useState(emptyLocation)
  const [contactForm, setContactForm] = useState(emptyContact)
  const [editingCustomerId, setEditingCustomerId] = useState(null)
  const [editingLocationId, setEditingLocationId] = useState(null)
  const [editingContactId, setEditingContactId] = useState(null)
  const [q, setQ] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [bulkCreatingCustomerId, setBulkCreatingCustomerId] = useState(null)
  const isAdmin = user?.role?.name === 'Admin'
  const canCreate = isAdmin || user?.role?.name === 'Irodai felhasználó'

  useEffect(() => { load() }, [q])

  async function load() {
    try {
      setCustomers(await api(`/customers?${new URLSearchParams(q ? { q } : {})}`))
    } catch (err) { setError(err.message) }
  }

  const contactCustomer = useMemo(
    () => customers.find((customer) => customer.id === Number(contactForm.customer_id)),
    [customers, contactForm.customer_id],
  )
  const contactLocations = (contactCustomer?.locations || []).filter(
    (location) => location.is_active !== false || (editingContactId && location.id === Number(contactForm.location_id)),
  )

  function setCustomerField(k, v) { setCustomerForm((p) => ({ ...p, [k]: v })) }
  function setLocationField(k, v) { setLocationForm((p) => ({ ...p, [k]: v })) }
  function setContactField(k, v) { setContactForm((p) => ({ ...p, [k]: v })) }

  async function submitCustomer(e) {
    e.preventDefault(); setError('')
    const payload = { ...customerForm, email: customerForm.email || null, company_code: customerForm.company_code || null }
    try {
      if (editingCustomerId) await api(`/customers/${editingCustomerId}`, { method: 'PUT', body: payload })
      else await api('/customers', { method: 'POST', body: payload })
      setCustomerForm(emptyCustomer); setEditingCustomerId(null); load()
    } catch (err) { setError(err.message) }
  }

  async function submitLocation(e) {
    e.preventDefault(); setError('')
    try {
      const customerId = Number(locationForm.customer_id)
      const payload = {
        name: locationForm.name,
        address: locationForm.address || null,
        gps_lat: locationForm.gps_lat || null,
        gps_lng: locationForm.gps_lng || null,
        note: locationForm.note || null,
      }
      if (editingLocationId) await api(`/locations/${editingLocationId}`, { method: 'PUT', body: payload })
      else await api(`/customers/${customerId}/locations`, { method: 'POST', body: { ...payload, customer_id: customerId } })
      setLocationForm(emptyLocation); setEditingLocationId(null); load()
    } catch (err) { setError(err.message) }
  }

  async function submitContact(e) {
    e.preventDefault(); setError('')
    try {
      const customerId = Number(contactForm.customer_id)
      const payload = {
        category: contactForm.category,
        name: contactForm.name,
        title: contactForm.title || null,
        phone: contactForm.phone || null,
        email: contactForm.email || null,
        location_id: contactForm.location_id ? Number(contactForm.location_id) : null,
        note: contactForm.note || null,
        is_primary: Boolean(contactForm.is_primary),
      }
      if (editingContactId) await api(`/customers/${customerId}/contacts/${editingContactId}`, { method: 'PUT', body: payload })
      else await api(`/customers/${customerId}/contacts`, { method: 'POST', body: payload })
      setContactForm({ ...emptyContact, customer_id: String(customerId), category: contactForm.category })
      setEditingContactId(null)
      load()
    } catch (err) { setError(err.message) }
  }

  function editCustomer(row) {
    setEditingCustomerId(row.id)
    setCustomerForm(Object.fromEntries(Object.keys(emptyCustomer).map((key) => [key, row[key] || ''])))
  }
  function editLocation(customer, location) {
    setEditingLocationId(location.id)
    setLocationForm({
      customer_id: String(customer.id),
      name: location.name || '',
      address: location.address || '',
      gps_lat: location.gps_lat || '',
      gps_lng: location.gps_lng || '',
      note: location.note || '',
    })
  }
  function editContact(customer, contact) {
    setEditingContactId(contact.id)
    setContactForm({
      customer_id: String(customer.id),
      location_id: contact.location_id ? String(contact.location_id) : '',
      category: contact.category || 'Szerviz',
      name: contact.name || '',
      title: contact.title || '',
      phone: contact.phone || '',
      email: contact.email || '',
      note: contact.note || '',
      is_primary: Boolean(contact.is_primary),
    })
  }
  async function removeCustomer(row) {
    if (!confirm('Biztosan törlöd az ügyfelet és a hozzá tartozó, nem hivatkozott adatokat?')) return
    try { await api(`/customers/${row.id}`, { method: 'DELETE' }); load() } catch (err) { setError(err.message) }
  }
  async function removeLocation(location) {
    if (!confirm(`Biztosan törlöd ezt a helyszínt: ${location.name}?`)) return
    try { await api(`/locations/${location.id}`, { method: 'DELETE' }); load() } catch (err) { setError(err.message) }
  }
  async function toggleLocation(location) {
    const nextActive = location.is_active === false
    const question = nextActive
      ? `Visszaaktiválod ezt a helyszínt: ${location.name}?`
      : `Inaktiválod ezt a helyszínt: ${location.name}?\n\nA korábbi adatok megmaradnak, de új munkalaphoz, eszközhöz, kapcsolattartóhoz vagy szerződéshez nem lesz választható.`
    if (!confirm(question)) return
    try {
      await api(`/locations/${location.id}`, { method: 'PUT', body: { is_active: nextActive } })
      await load()
    } catch (err) { setError(err.message) }
  }
  async function removeContact(customerId, contactId) {
    if (!confirm('Biztosan törlöd a kapcsolattartót?')) return
    try {
      await api(`/customers/${customerId}/contacts/${contactId}`, { method: 'DELETE' })
      load()
    } catch (err) { setError(err.message) }
  }

  async function createMaintenanceWorkOrders(customer) {
    const confirmed = confirm(
      `Létrehozod a karbantartási munkalapokat a(z) ${customer.name} összes eszközéhez?\n\n` +
      'Azok az eszközök kimaradnak, amelyekhez már van nyitott karbantartási munkalap.'
    )
    if (!confirmed) return
    setError('')
    setSuccess('')
    setBulkCreatingCustomerId(customer.id)
    try {
      const result = await api(`/customers/${customer.id}/maintenance-work-orders`, { method: 'POST' })
      const summary = `${result.created_count} munkalap létrehozva, ${result.skipped_count} kihagyva.`
      if (!result.created_count) {
        setSuccess(summary)
        return
      }
      sessionStorage.setItem('bulkWorkOrderSelection', JSON.stringify(result.created_work_order_ids))
      navigate(`/work-orders?bulk_created=${result.created_count}&bulk_skipped=${result.skipped_count}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBulkCreatingCustomerId(null)
    }
  }

  return (
    <section>
      <div className="page-head"><h1>Ügyfelek, helyszínek és kapcsolattartók</h1></div>
      {error && <div className="error">{error}</div>}
      {success && <div className="success">{success}</div>}
      {canCreate && <div className="two-col">
        <div className="panel">
          <h2>{editingCustomerId ? 'Ügyfél szerkesztése' : 'Új ügyfél'}</h2>
          <form className="grid-form one" onSubmit={submitCustomer}>
            <Field label="Név"><input value={customerForm.name} onChange={(e) => setCustomerField('name', e.target.value)} required /></Field>
            <Field label="Cég"><input value={customerForm.company_code || ''} onChange={(e) => setCustomerField('company_code', e.target.value)} placeholder="pl. DRh, SP, GXR" /></Field>
            <Field label="Régi fő kapcsolattartó"><input value={customerForm.contact_person || ''} onChange={(e) => setCustomerField('contact_person', e.target.value)} /></Field>
            <Field label="Telefon"><input value={customerForm.phone || ''} onChange={(e) => setCustomerField('phone', e.target.value)} /></Field>
            <Field label="Email"><input type="email" value={customerForm.email || ''} onChange={(e) => setCustomerField('email', e.target.value)} /></Field>
            <Field label="Cím"><input value={customerForm.address || ''} onChange={(e) => setCustomerField('address', e.target.value)} /></Field>
            <Field label="Megjegyzés"><textarea value={customerForm.note || ''} onChange={(e) => setCustomerField('note', e.target.value)} /></Field>
            <div className="form-actions"><button>{editingCustomerId ? 'Mentés' : 'Létrehozás'}</button>{editingCustomerId && <button type="button" className="secondary" onClick={() => { setEditingCustomerId(null); setCustomerForm(emptyCustomer) }}>Mégse</button>}</div>
          </form>
        </div>
        <div className="panel">
          <h2>{editingLocationId ? 'Helyszín szerkesztése' : 'Új helyszín'}</h2>
          <form className="grid-form one" onSubmit={submitLocation}>
            <Field label="Ügyfél"><select value={locationForm.customer_id} onChange={(e) => setLocationField('customer_id', e.target.value)} required disabled={Boolean(editingLocationId)}><option value="">Válassz ügyfelet</option>{customers.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}</select></Field>
            <Field label="Név"><input value={locationForm.name} onChange={(e) => setLocationField('name', e.target.value)} required /></Field>
            <Field label="Cím"><input value={locationForm.address} onChange={(e) => setLocationField('address', e.target.value)} /></Field>
            <Field label="GPS szélesség"><input value={locationForm.gps_lat} onChange={(e) => setLocationField('gps_lat', e.target.value)} /></Field>
            <Field label="GPS hosszúság"><input value={locationForm.gps_lng} onChange={(e) => setLocationField('gps_lng', e.target.value)} /></Field>
            <Field label="Megjegyzés"><textarea value={locationForm.note} onChange={(e) => setLocationField('note', e.target.value)} /></Field>
            <div className="form-actions"><button>{editingLocationId ? 'Helyszín mentése' : 'Helyszín hozzáadása'}</button>{editingLocationId && <button type="button" className="secondary" onClick={() => { setEditingLocationId(null); setLocationForm(emptyLocation) }}>Mégse</button>}</div>
          </form>
        </div>
      </div>}

      {canCreate && <div className="panel">
        <h2>{editingContactId ? 'Kapcsolattartó szerkesztése' : 'Új kapcsolattartó'}</h2>
        <form className="grid-form" onSubmit={submitContact}>
          <Field label="Ügyfél"><select value={contactForm.customer_id} onChange={(e) => setContactForm({ ...contactForm, customer_id: e.target.value, location_id: '' })} required disabled={Boolean(editingContactId)}><option value="">Válassz ügyfelet</option>{customers.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}</select></Field>
          <Field label="Kategória"><select value={contactForm.category} onChange={(e) => setContactField('category', e.target.value)}>{contactCategories.map(category => <option key={category}>{category}</option>)}</select></Field>
          <Field label="Helyszín"><select value={contactForm.location_id || ''} onChange={(e) => setContactField('location_id', e.target.value)} disabled={!contactForm.customer_id}><option value="">Általános ügyfélkapcsolat</option>{contactLocations.map(location => <option key={location.id} value={location.id}>{location.name} - {location.address || 'nincs cím'}</option>)}</select></Field>
          <Field label="Név"><input value={contactForm.name} onChange={(e) => setContactField('name', e.target.value)} required /></Field>
          <Field label="Beosztás / megjegyzett szerep"><input value={contactForm.title || ''} onChange={(e) => setContactField('title', e.target.value)} /></Field>
          <Field label="Telefon"><input value={contactForm.phone || ''} onChange={(e) => setContactField('phone', e.target.value)} /></Field>
          <Field label="Email"><input type="email" value={contactForm.email || ''} onChange={(e) => setContactField('email', e.target.value)} /></Field>
          <Field label="Elsődleges"><label className="checkbox-line"><input type="checkbox" checked={contactForm.is_primary} onChange={(e) => setContactField('is_primary', e.target.checked)} /> elsődleges ebben a kategóriában</label></Field>
          <Field label="Megjegyzés"><textarea value={contactForm.note || ''} onChange={(e) => setContactField('note', e.target.value)} /></Field>
          <div className="form-actions"><button>{editingContactId ? 'Kapcsolattartó mentése' : 'Kapcsolattartó hozzáadása'}</button>{editingContactId && <button type="button" className="secondary" onClick={() => { setEditingContactId(null); setContactForm(emptyContact) }}>Mégse</button>}</div>
        </form>
      </div>}

      <div className="filters"><input placeholder="Ügyfél vagy kapcsolattartó keresése" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <DataTable rows={customers} columns={[
        { key: 'company_code', label: 'Cég' },
        { key: 'name', label: 'Név' },
        { key: 'contact_person', label: 'Régi fő kontakt' },
        { key: 'phone', label: 'Telefon' },
        { key: 'email', label: 'Email' },
        { key: 'address', label: 'Cím' },
        { key: 'locations', label: 'Helyszínek', render: row => <LocationList customer={row} canManage={isAdmin} onEdit={editLocation} onDelete={removeLocation} onToggle={toggleLocation} /> },
        { key: 'contacts', label: 'Kapcsolattartók', render: row => <ContactList customer={row} canManage={isAdmin} onEdit={editContact} onDelete={removeContact} /> },
      ]} actions={(row) => <>
        {user?.role?.name !== 'Technikus / szerelő' && <button disabled={bulkCreatingCustomerId === row.id} onClick={() => createMaintenanceWorkOrders(row)}>{bulkCreatingCustomerId === row.id ? 'Létrehozás...' : 'Karbantartási munkalapok'}</button>}
        {isAdmin && <button onClick={() => editCustomer(row)}>Szerkesztés</button>}
        {isAdmin && <button className="danger" onClick={() => removeCustomer(row)}>Törlés</button>}
      </>} />
    </section>
  )
}

function LocationList({ customer, canManage, onEdit, onDelete, onToggle }) {
  const locations = customer.locations || []
  if (!locations.length) return '-'
  return (
    <div className="contact-list-inline">
      {locations.map((location) => (
        <div className="contact-chip" key={location.id}>
          <strong>{location.name}</strong>
          {location.address ? ` · ${location.address}` : ''}
          {location.is_active === false ? ' · inaktív' : ''}
          {canManage && <button type="button" className="link-button" onClick={() => onEdit(customer, location)}>szerkesztés</button>}
          {canManage && <button type="button" className="link-button" onClick={() => onToggle(location)}>{location.is_active === false ? 'aktiválás' : 'inaktiválás'}</button>}
          {canManage && <button type="button" className="link-button danger-text" onClick={() => onDelete(location)}>törlés</button>}
        </div>
      ))}
    </div>
  )
}

function ContactList({ customer, canManage, onEdit, onDelete }) {
  const contacts = customer.contacts || []
  if (!contacts.length) return '-'
  return (
    <div className="contact-list-inline">
      {contacts.map((contact) => (
        <div className="contact-chip" key={contact.id}>
          <strong>{contact.category}</strong>: {contact.name}
          {contact.is_primary ? ' · elsődleges' : ''}
          {contact.location_name ? ` · ${contact.location_name}` : ''}
          {contact.phone ? ` · ${contact.phone}` : ''}
          {contact.email ? ` · ${contact.email}` : ''}
          {canManage && <button type="button" className="link-button" onClick={() => onEdit(customer, contact)}>szerkesztés</button>}
          {canManage && <button type="button" className="link-button danger-text" onClick={() => onDelete(customer.id, contact.id)}>törlés</button>}
        </div>
      ))}
    </div>
  )
}
