import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, downloadFile } from '../api.js'
import { hasPermission } from '../utils/permissions.js'

const STATUS_LABELS = { pending: 'Jóváhagyásra vár', approved: 'Jóváhagyva', rejected: 'Elutasítva', withdrawn: 'Visszavonva' }
const MAX_FILE_SIZE = 25 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.csv', '.jpg', '.jpeg', '.png']

function money(value, currency = 'HUF') {
  const amount = Number(value)
  try { return new Intl.NumberFormat('hu-HU', { style: 'currency', currency, maximumFractionDigits: 2 }).format(amount) }
  catch { return `${amount.toLocaleString('hu-HU')} ${currency}` }
}
function when(value) { return value ? new Date(value).toLocaleString('hu-HU') : '–' }
function fileSize(bytes) { return `${(Number(bytes) / 1024 / 1024).toFixed(2)} MB` }

export default function ProcurementDetail({ user }) {
  const { requestId } = useParams()
  const navigate = useNavigate()
  const [row, setRow] = useState(null)
  const [comment, setComment] = useState('')
  const [files, setFiles] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    setError('')
    try { setRow(await api(`/procurement/requests/${requestId}`)) }
    catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [requestId])

  async function decide(decision) {
    if (decision === 'reject' && !comment.trim()) { setError('Elutasításkor a jóváhagyói megjegyzés kötelező.'); return }
    setBusy(true); setError('')
    try {
      const updated = await api(`/procurement/requests/${row.id}/${decision}`, { method: 'POST', body: { version: row.version, comment } })
      setRow(updated); setComment(''); window.dispatchEvent(new CustomEvent('app:notifications-changed'))
    } catch (err) { setError(err.message); if (err.status === 409) await load() }
    finally { setBusy(false) }
  }

  async function withdraw() {
    if (!confirm('Biztosan visszavonod ezt a beszerzési igényt?')) return
    setBusy(true); setError('')
    try { setRow(await api(`/procurement/requests/${row.id}/withdraw`, { method: 'POST', body: { version: row.version } })); window.dispatchEvent(new CustomEvent('app:notifications-changed')) }
    catch (err) { setError(err.message); if (err.status === 409) await load() }
    finally { setBusy(false) }
  }

  function selectFiles(event) {
    const selected = [...event.target.files]
    for (const file of selected) {
      const lower = file.name.toLowerCase()
      if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) { setError(`${file.name}: nem engedélyezett fájlformátum.`); return }
      if (file.size > MAX_FILE_SIZE) { setError(`${file.name}: a fájl mérete meghaladja a 25 MB-ot.`); return }
    }
    setError(''); setFiles(selected)
  }

  async function upload() {
    if (!files.length) return
    setBusy(true); setError('')
    try {
      for (const file of files) {
        const data = new FormData()
        data.append('files', file)
        await api(`/procurement/requests/${row.id}/attachments`, { method: 'POST', body: data })
      }
      setFiles([]); await load()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  if (!row) return <section><div className="page-head"><h1>Beszerzési igény</h1></div>{error ? <div className="error">{error}</div> : <div className="panel">Betöltés...</div>}</section>

  const isOwner = row.requester_user_id === user?.id
  const canApprove = hasPermission(user, 'procurement.approve') && !isOwner && row.status === 'pending'

  return (
    <section className="procurement-page">
      <div className="page-head"><div><h1>{row.request_number}</h1><p className="muted">{row.subject}</p></div><button className="secondary" onClick={() => navigate(hasPermission(user, 'procurement.approve') ? '/procurement/approvals' : '/procurement')}>Vissza a listához</button></div>
      {error && <div className="error">{error}</div>}
      <div className="panel procurement-detail-grid">
        <div><span className="detail-label">Kérelmező</span><strong>{row.requester?.full_name}</strong></div>
        <div><span className="detail-label">Státusz</span><strong><span className={`procurement-status status-${row.status}`}>{STATUS_LABELS[row.status]}</span></strong></div>
        <div><span className="detail-label">Összérték</span><strong>{money(row.total_amount, row.currency)}</strong></div>
        <div><span className="detail-label">Beküldve</span><strong>{when(row.submitted_at)}</strong></div>
        <div><span className="detail-label">Jóváhagyó</span><strong>{row.approver?.full_name || '–'}</strong></div>
        <div><span className="detail-label">Döntés</span><strong>{when(row.decided_at)}</strong></div>
      </div>
      <div className="panel"><h2>Beszerzés célja</h2><p className="preserve-lines">{row.purpose}</p><h2>Igény részletes leírása</h2><p className="preserve-lines">{row.description}</p></div>
      <div className="panel">
        <h2>Csatolmányok</h2>
        {row.attachments?.length ? <ul className="attachment-list">{row.attachments.map((file) => <li key={file.id}><button className="link-button" onClick={() => downloadFile(`/procurement/attachments/${file.id}/download`, file.original_filename)}>{file.original_filename}</button><span>{fileSize(file.size_bytes)}</span></li>)}</ul> : <p className="muted">Nincs csatolmány.</p>}
        {isOwner && row.status === 'pending' && <div className="attachment-upload"><input type="file" multiple accept=".pdf,.docx,.xlsx,.csv,.jpg,.jpeg,.png" onChange={selectFiles} />{files.length > 0 && <button type="button" onClick={upload} disabled={busy}>Kiválasztott fájlok feltöltése</button>}</div>}
      </div>
      {(row.approver_comment || canApprove) && <div className="panel"><h2>Jóváhagyás</h2>{row.approver_comment && <p className="preserve-lines"><strong>Megjegyzés:</strong> {row.approver_comment}</p>}{canApprove && <><label>Jóváhagyói megjegyzés<textarea rows={4} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Elutasításkor kötelező" /></label><div className="form-actions"><button onClick={() => decide('approve')} disabled={busy}>Jóváhagyás</button><button className="danger" onClick={() => decide('reject')} disabled={busy}>Elutasítás</button></div></>}</div>}
      {isOwner && row.status === 'pending' && <div className="panel"><button className="danger" onClick={withdraw} disabled={busy}>Beszerzési igény visszavonása</button></div>}
    </section>
  )
}
