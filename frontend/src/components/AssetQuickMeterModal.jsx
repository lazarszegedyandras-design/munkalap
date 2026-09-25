import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Field } from './FormField.jsx'
import { assetLabel } from '../utils/assets.js'

export default function AssetQuickMeterModal({ asset, onClose, onSaved }) {
  const [tracking, setTracking] = useState(null)
  const [workOrders, setWorkOrders] = useState([])
  const [form, setForm] = useState({ value: '', black_white_value: '', color_value: '', scan_value: '', recorded_at: '', work_order_id: '', note: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const [overview, orders] = await Promise.all([
          api(`/assets/${asset.id}/printer-tracking`),
          api(`/assets/${asset.id}/work-orders`),
        ])
        if (!active) return
        setTracking(overview)
        setWorkOrders(orders)
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [asset.id])

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const updated = await api(`/assets/${asset.id}/meter-readings`, {
        method: 'POST',
        body: {
          value: Number(form.value),
          black_white_value: form.black_white_value === '' ? null : Number(form.black_white_value),
          color_value: form.color_value === '' ? null : Number(form.color_value),
          scan_value: form.scan_value === '' ? null : Number(form.scan_value),
          recorded_at: form.recorded_at || null,
          work_order_id: form.work_order_id ? Number(form.work_order_id) : null,
          note: form.note || null,
        },
      })
      onSaved?.(updated)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="quick-meter-title">
        <div className="modal-head">
          <div>
            <h2 id="quick-meter-title">Számlálóállás rögzítése</h2>
            <p className="muted">{assetLabel(asset)}</p>
          </div>
          <button type="button" className="icon-button" aria-label="Bezárás" onClick={onClose}>×</button>
        </div>
        {error && <div className="error">{error}</div>}
        {loading ? <p>Adatok betöltése...</p> : <form className="stack-form" onSubmit={submit}>
          <div className="quick-meter-current">
            <span>Előző állás</span>
            <strong>{tracking?.latest_meter ? meterSummary(tracking.latest_meter) : 'Nincs korábbi adat'}</strong>
          </div>
          <Field label="Összes számláló"><input autoFocus type="number" min={tracking?.latest_meter?.value ?? 0} required value={form.value} onChange={(event) => setForm({ ...form, value: event.target.value })} /></Field>
          <div className="grid-form meter-channel-grid">
            <Field label="FF számláló"><input type="number" min="0" value={form.black_white_value} onChange={(event) => setForm({ ...form, black_white_value: event.target.value })} /></Field>
            <Field label="Színes számláló"><input type="number" min="0" value={form.color_value} onChange={(event) => setForm({ ...form, color_value: event.target.value })} /></Field>
            <Field label="Scan számláló"><input type="number" min="0" value={form.scan_value} onChange={(event) => setForm({ ...form, scan_value: event.target.value })} /></Field>
          </div>
          <Field label="Mérés időpontja"><input type="datetime-local" value={form.recorded_at} onChange={(event) => setForm({ ...form, recorded_at: event.target.value })} /></Field>
          <Field label="Kapcsolódó munkalap"><select value={form.work_order_id} onChange={(event) => setForm({ ...form, work_order_id: event.target.value })}><option value="">Nincs</option>{workOrders.map((order) => <option value={order.id} key={order.id}>{order.number} – {order.description}</option>)}</select></Field>
          <Field label="Megjegyzés"><textarea rows="3" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} /></Field>
          <div className="form-actions modal-actions"><button type="button" className="secondary" onClick={onClose}>Mégse</button><button disabled={saving}>{saving ? 'Rögzítés...' : 'Rögzítés'}</button></div>
        </form>}
      </div>
    </div>
  )
}

function formatInteger(value) {
  return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(value))
}

function meterSummary(reading) {
  const parts = [`Összes: ${formatInteger(reading.value)}`]
  if (reading.black_white_value !== null && reading.black_white_value !== undefined) parts.push(`FF: ${formatInteger(reading.black_white_value)}`)
  if (reading.color_value !== null && reading.color_value !== undefined) parts.push(`Színes: ${formatInteger(reading.color_value)}`)
  if (reading.scan_value !== null && reading.scan_value !== undefined) parts.push(`Scan: ${formatInteger(reading.scan_value)}`)
  return parts.join(' · ')
}
