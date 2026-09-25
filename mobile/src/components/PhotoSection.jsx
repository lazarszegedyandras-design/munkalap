import { useEffect, useState } from 'react'
import { captureWorkOrderPhoto } from '../services/camera.js'
import { PHOTO_LABELS, canEditWorkOrder } from '../services/format.js'
import { apiBlob } from '../services/api.js'

function PhotoThumb({ orderId, photo }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    let active = true; let objectUrl = null
    apiBlob(`/work-orders/${orderId}/photos/${photo.id}/content`).then(blob => {
      if (!active) return
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl)
    }).catch(() => {})
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [orderId, photo.id])
  return url ? <img className="photo-thumb" src={url} alt={PHOTO_LABELS[photo.category] || 'Munkalap fénykép'} /> : <div className="photo-placeholder">📷</div>
}

export default function PhotoSection({ order, api, onChanged }) {
  const [category, setCategory] = useState('other')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const editable = canEditWorkOrder(order.status)
  async function takePhoto() {
    setError(''); setBusy(true)
    try {
      const file = await captureWorkOrderPhoto()
      const form = new FormData(); form.append('category', category); if (note.trim()) form.append('note', note.trim()); form.append('photo', file)
      await api(`/work-orders/${order.id}/photos`, { method: 'POST', body: form })
      setNote(''); await onChanged()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function remove(id) {
    if (!confirm('Törlöd ezt a fényképet?')) return
    setBusy(true); setError('')
    try { await api(`/work-orders/${order.id}/photos/${id}`, { method: 'DELETE' }); await onChanged() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="panel"><h2>Fényképek</h2>
    <div className="photo-grid">{(order.photos || []).map(p => <div className="photo-item" key={p.id}><PhotoThumb orderId={order.id} photo={p}/><strong>{PHOTO_LABELS[p.category] || p.category}</strong><small>{p.note || `${p.width}×${p.height}`}</small>{editable && <button className="text-danger" onClick={() => remove(p.id)}>Törlés</button>}</div>)}</div>
    {editable && <div className="stack compact"><select value={category} onChange={e => setCategory(e.target.value)}>{Object.entries(PHOTO_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select><input placeholder="Megjegyzés (opcionális)" value={note} onChange={e => setNote(e.target.value)} /><button className="btn secondary" onClick={takePhoto} disabled={busy}>{busy ? 'Feltöltés…' : '📷 Fénykép készítése'}</button></div>}
    {error && <div className="error-box">{error}</div>}
  </section>
}
