import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Field } from './FormField.jsx'
import { assetLabel } from '../utils/assets.js'

export default function WorkOrderArchiveUploadModal({ targetType, targetId, title, defaultSourceNumber = '', defaultWorkDate = '', assets = [], onClose, onSaved }) {
  const globalUpload = targetType === 'global'
  const [file, setFile] = useState(null)
  const [assetId, setAssetId] = useState('')
  const [workOrderId, setWorkOrderId] = useState('')
  const [workOrders, setWorkOrders] = useState([])
  const [workOrdersLoading, setWorkOrdersLoading] = useState(false)
  const [sourceNumber, setSourceNumber] = useState(defaultSourceNumber || '')
  const [workDate, setWorkDate] = useState(defaultWorkDate ? String(defaultWorkDate).slice(0, 10) : '')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!globalUpload || !assetId) {
      setWorkOrders([])
      setWorkOrderId('')
      return undefined
    }
    let active = true
    setWorkOrdersLoading(true)
    api(`/work-orders?asset_id=${encodeURIComponent(assetId)}`)
      .then((rows) => { if (active) setWorkOrders(rows) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setWorkOrdersLoading(false) })
    return () => { active = false }
  }, [globalUpload, assetId])

  async function submit(event) {
    event.preventDefault()
    if (!file) {
      setError('Válassz feltöltendő fájlt.')
      return
    }
    if (globalUpload && !assetId) {
      setError('Válassz eszközt az archív munkalaphoz.')
      return
    }
    setSaving(true)
    setError('')
    const form = new FormData()
    form.append('archive_file', file)
    if (globalUpload) {
      form.append('asset_id', assetId)
      if (workOrderId) form.append('work_order_id', workOrderId)
    }
    if (sourceNumber.trim()) form.append('source_number', sourceNumber.trim())
    if (workDate) form.append('work_date', workDate)
    if (note.trim()) form.append('note', note.trim())
    const path = globalUpload
      ? '/work-order-archives'
      : targetType === 'asset'
        ? `/assets/${targetId}/work-order-archives`
        : `/work-orders/${targetId}/archives`
    try {
      const created = await api(path, { method: 'POST', body: form })
      onSaved(created)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return <div className="modal-backdrop no-print" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) onClose() }}>
    <form className="modal-card archive-upload-modal" onSubmit={submit}>
      <div className="modal-head"><div><h2>{title}</h2><p>PDF, JPG vagy PNG fájl tölthető fel. Az alapértelmezett méretkorlát 25 MB.</p></div><button type="button" className="secondary" disabled={saving} onClick={onClose}>Bezárás</button></div>
      {error && <div className="error">{error}</div>}
      {globalUpload && <>
        <Field label="Eszköz"><select required value={assetId} onChange={(event) => { setAssetId(event.target.value); setWorkOrderId('') }}><option value="">Válassz eszközt</option>{assets.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}</select></Field>
        <Field label="Digitális munkalap"><select value={workOrderId} disabled={!assetId || workOrdersLoading} onChange={(event) => setWorkOrderId(event.target.value)}><option value="">Nincs – korábbi nyilvántartás</option>{workOrders.map((order) => <option key={order.id} value={order.id}>{order.number} · {order.description || 'Nincs leírás'} · {order.status}</option>)}</select>{assetId && <small>{workOrdersLoading ? 'Kapcsolódó munkalapok betöltése...' : `${workOrders.length} kapcsolódó digitális munkalap`}</small>}</Field>
      </>}
      <Field label="Fájl"><input type="file" required accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={(event) => setFile(event.target.files?.[0] || null)} /></Field>
      <Field label="Eredeti munkalapszám"><input maxLength="100" value={sourceNumber} onChange={(event) => setSourceNumber(event.target.value)} placeholder="Ha ismert" /></Field>
      <Field label="Munkalap dátuma"><input type="date" value={workDate} onChange={(event) => setWorkDate(event.target.value)} /></Field>
      <Field label="Megjegyzés"><textarea rows="4" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Opcionális" /></Field>
      <div className="inline-actions modal-actions"><button type="button" className="secondary" disabled={saving} onClick={onClose}>Mégse</button><button type="submit" disabled={saving}>{saving ? 'Feltöltés...' : 'Archiválás'}</button></div>
    </form>
  </div>
}
