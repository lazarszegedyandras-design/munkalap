import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { Field } from '../components/FormField.jsx'

const emptyAsset = {
  internal_id: '', serial_number: '', type: '', manufacturer: '', model: '', category: '', status: 'aktív',
  current_location_id: '', customer_id: '', internal_use: false, purchase_date: '', warranty_expiry: '',
  last_maintenance_date: '', maintenance_cycle_months: '', maintenance_cycle_note: '', next_maintenance_date: '', note: '',
}
const statuses = ['aktív', 'hibás', 'javítás alatt', 'selejtezett', 'raktáron']

export default function AssetForm({ user }) {
  const { assetId } = useParams()
  const navigate = useNavigate()
  const editing = Boolean(assetId)
  const [form, setForm] = useState(emptyAsset)
  const [customers, setCustomers] = useState([])
  const [locations, setLocations] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const canEdit = ['Admin', 'Irodai felhasználó'].includes(user?.role?.name)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      try {
        const requests = [api('/customers'), api('/locations')]
        if (editing) requests.push(api(`/assets/${assetId}`))
        const [customerRows, locationRows, asset] = await Promise.all(requests)
        if (!active) return
        setCustomers(customerRows)
        setLocations(locationRows)
        if (asset) {
          setForm({
            ...emptyAsset,
            ...asset,
            customer_id: asset.customer_id || '',
            current_location_id: asset.current_location_id || '',
            maintenance_cycle_months: asset.maintenance_cycle_months || '',
          })
        }
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [assetId, editing])

  const allowedLocations = useMemo(
    () => locations.filter((location) => (
      (!form.customer_id || location.customer_id === Number(form.customer_id))
      && (location.is_active !== false || (editing && location.id === Number(form.current_location_id)))
    )),
    [locations, form.customer_id, form.current_location_id, editing],
  )

  function setField(name, value) {
    setForm((previous) => ({ ...previous, [name]: value }))
  }

  function normalize(payload) {
    const out = { ...payload }
    ;['customer_id', 'current_location_id'].forEach((key) => { out[key] = out[key] ? Number(out[key]) : null })
    out.maintenance_cycle_months = out.maintenance_cycle_months ? Number(out.maintenance_cycle_months) : null
    ;['purchase_date', 'warranty_expiry', 'last_maintenance_date', 'next_maintenance_date'].forEach((key) => { out[key] = out[key] || null })
    delete out.id
    delete out.created_at
    delete out.updated_at
    delete out.customer_name
    delete out.location_name
    delete out.company_code
    delete out.import_source
    delete out.import_batch
    delete out.import_row
    delete out.display_internal_id
    delete out.internal_id_hidden
    delete out.display_name
    delete out.maintenance_cycle_label
    delete out.calculated_next_maintenance_date
    delete out.effective_next_maintenance_date
    delete out.maintenance_due_source
    delete out.maintenance_days_since_last
    delete out.maintenance_days_until_due
    delete out.maintenance_state
    delete out.maintenance_state_label
    delete out.latest_meter_value
    delete out.latest_meter_at
    delete out.meter_age_days
    delete out.meter_state
    delete out.meter_state_label
    delete out.average_monthly_usage
    delete out.next_component_name
    delete out.next_component_forecast_at
    delete out.component_forecast_status
    delete out.component_forecast_status_label
    delete out.component_due_count
    return out
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      const saved = editing
        ? await api(`/assets/${assetId}`, { method: 'PUT', body: normalize(form) })
        : await api('/assets', { method: 'POST', body: normalize(form) })
      navigate(`/assets/${saved.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!canEdit) return <div className="error">Nincs jogosultságod eszköz létrehozására vagy szerkesztésére.</div>
  if (loading) return <div className="panel">Eszközadatok betöltése...</div>

  return (
    <section className="asset-form-page">
      <div className="page-head">
        <div>
          <Link className="breadcrumb" to={editing ? `/assets/${assetId}` : '/assets'}>← Vissza az eszközökhöz</Link>
          <h1>{editing ? 'Eszköz szerkesztése' : 'Új eszköz'}</h1>
          <p className="muted">A mezők logikai csoportokba rendezve jelennek meg.</p>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      <form onSubmit={submit}>
        <div className="asset-form-sections">
          <section className="panel asset-form-section">
            <h2>Azonosítás</h2>
            <div className="grid-form">
              {(!editing || !form.internal_id_hidden) && <Field label="Belső azonosító"><input required value={form.internal_id} onChange={(event) => setField('internal_id', event.target.value)} /></Field>}
              <Field label="Gyári szám"><input value={form.serial_number || ''} onChange={(event) => setField('serial_number', event.target.value)} /></Field>
              <Field label="Gyártó"><input value={form.manufacturer || ''} onChange={(event) => setField('manufacturer', event.target.value)} /></Field>
              <Field label="Modell"><input value={form.model || ''} onChange={(event) => setField('model', event.target.value)} /></Field>
              <Field label="Típus"><input value={form.type || ''} onChange={(event) => setField('type', event.target.value)} /></Field>
              <Field label="Kategória"><input value={form.category || ''} onChange={(event) => setField('category', event.target.value)} /></Field>
            </div>
          </section>

          <section className="panel asset-form-section">
            <h2>Elhelyezés és tulajdon</h2>
            <div className="grid-form">
              <Field label="Állapot"><select value={form.status} onChange={(event) => setField('status', event.target.value)}>{statuses.map((value) => <option key={value}>{value}</option>)}</select></Field>
              <Field label="Ügyfél"><select value={form.customer_id || ''} onChange={(event) => { setField('customer_id', event.target.value); setField('current_location_id', '') }}><option value="">Belső használat / nincs</option>{customers.map((customer) => <option value={customer.id} key={customer.id}>{customer.company_code ? `${customer.company_code} · ` : ''}{customer.name}</option>)}</select></Field>
              <Field label="Helyszín"><select value={form.current_location_id || ''} onChange={(event) => setField('current_location_id', event.target.value)}><option value="">Nincs</option>{allowedLocations.map((location) => <option value={location.id} key={location.id}>{location.name}{location.address ? ` · ${location.address}` : ''}{location.is_active === false ? ' · inaktív (meglévő)' : ''}</option>)}</select></Field>
              <label className="checkbox"><input type="checkbox" checked={form.internal_use} onChange={(event) => setField('internal_use', event.target.checked)} /> Belső használat</label>
            </div>
          </section>

          <section className="panel asset-form-section">
            <h2>Életciklus</h2>
            <div className="grid-form">
              <Field label="Vásárlás dátuma"><input type="date" value={form.purchase_date || ''} onChange={(event) => setField('purchase_date', event.target.value)} /></Field>
              <Field label="Garancia lejárata"><input type="date" value={form.warranty_expiry || ''} onChange={(event) => setField('warranty_expiry', event.target.value)} /></Field>
              <Field label="Utolsó karbantartás"><input type="date" value={form.last_maintenance_date || ''} onChange={(event) => setField('last_maintenance_date', event.target.value)} /></Field>
              <Field label="Szerződéses karbantartási ciklus (hónap)"><input type="number" min="1" max="120" value={form.maintenance_cycle_months || ''} onChange={(event) => setField('maintenance_cycle_months', event.target.value)} placeholder="Például: 3, 6 vagy 12" /></Field>
              <Field label="Ciklus megjegyzése"><input value={form.maintenance_cycle_note || ''} onChange={(event) => setField('maintenance_cycle_note', event.target.value)} placeholder="Például: megrendelés alapján" /></Field>
              <Field label="Következő karbantartás (kézi tartalék)"><input type="date" value={form.next_maintenance_date || ''} onChange={(event) => setField('next_maintenance_date', event.target.value)} disabled={Boolean(form.maintenance_cycle_months && form.last_maintenance_date)} /><small>A szerződéses ciklus és az utolsó karbantartás megadásakor a rendszer automatikusan számolja a következő dátumot.</small></Field>
              {editing && <Field label="Számított következő karbantartás"><input value={form.calculated_next_maintenance_date ? new Date(`${String(form.calculated_next_maintenance_date).slice(0, 10)}T00:00:00`).toLocaleDateString('hu-HU') : 'Nincs számítható dátum'} readOnly /></Field>}
            </div>
          </section>

          <section className="panel asset-form-section">
            <h2>Egyéb</h2>
            <Field label="Megjegyzés"><textarea rows="5" value={form.note || ''} onChange={(event) => setField('note', event.target.value)} /></Field>
          </section>
        </div>
        <div className="sticky-form-actions">
          <Link className="button secondary" to={editing ? `/assets/${assetId}` : '/assets'}>Mégse</Link>
          <button disabled={saving}>{saving ? 'Mentés...' : 'Mentés'}</button>
        </div>
      </form>
    </section>
  )
}
