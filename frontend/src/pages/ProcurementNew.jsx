import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

const MAX_FILE_SIZE = 25 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.csv', '.jpg', '.jpeg', '.png']

function validateFiles(files) {
  for (const file of files) {
    const name = file.name.toLowerCase()
    if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) return `${file.name}: nem engedélyezett fájlformátum.`
    if (file.size > MAX_FILE_SIZE) return `${file.name}: a fájl mérete meghaladja a 25 MB-ot.`
  }
  return ''
}

export default function ProcurementNew() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ subject: '', purpose: '', description: '', total_amount: '', currency: 'HUF' })
  const [files, setFiles] = useState([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function setField(key, value) { setForm((current) => ({ ...current, [key]: value })) }
  function chooseFiles(event) {
    const selected = [...event.target.files]
    const message = validateFiles(selected)
    if (message) { setError(message); event.target.value = ''; return }
    setError(''); setFiles(selected)
  }

  async function submit(event) {
    event.preventDefault(); setError('')
    const fileError = validateFiles(files)
    if (fileError) { setError(fileError); return }
    setSaving(true)
    let created = null
    try {
      created = await api('/procurement/requests', {
        method: 'POST',
        body: { ...form, total_amount: form.total_amount },
      })
      for (const file of files) {
        // Az Nginx általános API-limitje kérésenként 26 MiB, ezért több
        // 25 MiB-os csatolmányt külön multipart kérésekben töltünk fel.
        const data = new FormData()
        data.append('files', file)
        await api(`/procurement/requests/${created.id}/attachments`, { method: 'POST', body: data })
      }
      window.dispatchEvent(new CustomEvent('app:notifications-changed'))
      navigate(`/procurement/requests/${created.id}`)
    } catch (err) {
      if (created) {
        setError(`Az igény ${created.request_number} létrejött, de a csatolmány feltöltése sikertelen: ${err.message}. A részletező oldalon újra feltölthető.`)
      } else setError(err.message)
    } finally { setSaving(false) }
  }

  return (
    <section className="procurement-page">
      <div className="page-head"><div><h1>Új beszerzési igény</h1><p className="muted">A tárgy, a beszerzés célja, a részletes igény és az összérték kötelező.</p></div></div>
      {error && <div className="error">{error}</div>}
      <form className="panel procurement-form" onSubmit={submit}>
        <label>Tárgy<input value={form.subject} onChange={(e) => setField('subject', e.target.value)} maxLength={255} required /></label>
        <label>Beszerzés célja<textarea value={form.purpose} onChange={(e) => setField('purpose', e.target.value)} rows={3} required /></label>
        <label>Igény részletes leírása<textarea value={form.description} onChange={(e) => setField('description', e.target.value)} rows={10} required /></label>
        <div className="procurement-amount-row">
          <label>Összérték<input type="number" min="0.01" step="0.01" value={form.total_amount} onChange={(e) => setField('total_amount', e.target.value)} required /></label>
          <label>Pénznem<select value={form.currency} onChange={(e) => setField('currency', e.target.value)}><option value="HUF">HUF</option><option value="EUR">EUR</option><option value="USD">USD</option></select></label>
        </div>
        <label>Csatolmányok<input type="file" multiple accept=".pdf,.docx,.xlsx,.csv,.jpg,.jpeg,.png" onChange={chooseFiles} /><small>PDF, DOCX, XLSX, CSV, JPG vagy PNG; maximum 25 MB/fájl.</small></label>
        {files.length > 0 && <ul className="attachment-list">{files.map((file) => <li key={`${file.name}-${file.size}`}>{file.name} – {(file.size / 1024 / 1024).toFixed(2)} MB</li>)}</ul>}
        <div className="form-actions"><button disabled={saving}>{saving ? 'Beküldés...' : 'Beszerzési igény beküldése'}</button><button type="button" className="secondary" onClick={() => navigate('/procurement')}>Mégse</button></div>
      </form>
    </section>
  )
}
