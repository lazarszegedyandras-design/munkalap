import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

export default function WorkOrderArchiveTable({
  archives,
  loading = false,
  showWorkOrder = false,
  emptyText = 'Nincs archivált munkalap.',
  user = null,
  onDeleted = null,
}) {
  const [error, setError] = useState('')
  const [downloadingId, setDownloadingId] = useState(null)
  const [previewingId, setPreviewingId] = useState(null)
  const [preview, setPreview] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [locallyDeletedIds, setLocallyDeletedIds] = useState([])
  const canDelete = user?.role?.name === 'Admin'
  const visibleArchives = useMemo(
    () => (archives || []).filter((row) => !locallyDeletedIds.includes(row.id)),
    [archives, locallyDeletedIds],
  )

  useEffect(() => () => {
    if (preview?.url) URL.revokeObjectURL(preview.url)
  }, [preview])

  async function fetchArchiveBlob(row, mode = 'download') {
    const response = await api(`/work-order-archives/${row.id}/${mode}`)
    return response.blob()
  }

  async function download(row) {
    setError('')
    setDownloadingId(row.id)
    try {
      const blob = await fetchArchiveBlob(row)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = row.original_filename || `${row.archive_number}.pdf`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) {
      setError(err.message)
    } finally {
      setDownloadingId(null)
    }
  }

  async function openPreview(row) {
    setError('')
    setPreviewingId(row.id)
    try {
      const blob = await fetchArchiveBlob(row, 'preview')
      const url = URL.createObjectURL(blob)
      setPreview({ row, url, mimeType: blob.type || row.mime_type || '' })
    } catch (err) {
      setError(err.message)
    } finally {
      setPreviewingId(null)
    }
  }

  function closePreview() {
    setPreview(null)
  }

  function openDelete(row) {
    setError('')
    setDeleteConfirmation('')
    setDeleteTarget(row)
  }

  function closeDelete() {
    if (deleting) return
    setDeleteTarget(null)
    setDeleteConfirmation('')
  }

  async function confirmDelete(event) {
    event.preventDefault()
    if (!deleteTarget || deleteConfirmation !== 'TÖRÖL') return
    setDeleting(true)
    setError('')
    try {
      await api(`/work-order-archives/${deleteTarget.id}`, {
        method: 'DELETE',
        body: { confirmation: deleteConfirmation },
      })
      const deleted = deleteTarget
      setLocallyDeletedIds((current) => [...current, deleted.id])
      setDeleteTarget(null)
      setDeleteConfirmation('')
      onDeleted?.(deleted)
    } catch (err) {
      setError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  if (loading) return <div className="table-loading">Archívum betöltése...</div>
  return <>
    {error && <div className="error">{error}</div>}
    <div className="mini-table-wrap"><table className="mini-table archive-table"><thead><tr><th>Archív azonosító</th><th>Eredeti munkalap</th><th>Dátum</th>{showWorkOrder && <th>Digitális munkalap</th>}<th>Megjegyzés</th><th>Eszközök</th><th>Archiválva</th><th></th></tr></thead><tbody>
      {visibleArchives.length ? visibleArchives.map((row) => <tr key={row.id}>
        <td><strong>{row.archive_number}</strong></td>
        <td>{row.source_number || '—'}</td>
        <td>{formatDate(row.work_date)}</td>
        {showWorkOrder && <td>{row.work_order_number || 'Korábbi nyilvántartás'}</td>}
        <td><span className="archive-note" title={row.note || ''}>{row.note || '—'}</span></td>
        <td>{row.assets?.length ? row.assets.map((asset) => asset.display_name).join(', ') : '—'}</td>
        <td>{formatDateTime(row.created_at)}<small>{row.uploaded_by_name || 'Rendszer'}</small></td>
        <td><div className="archive-row-actions"><button type="button" className="secondary small-button" disabled={previewingId === row.id} onClick={() => openPreview(row)}>{previewingId === row.id ? 'Betöltés...' : 'Előnézet'}</button><button type="button" className="secondary small-button" disabled={downloadingId === row.id} onClick={() => download(row)}>{downloadingId === row.id ? 'Letöltés...' : 'Letöltés'}</button>{canDelete && <button type="button" className="danger small-button" onClick={() => openDelete(row)}>Törlés</button>}</div></td>
      </tr>) : <tr><td colSpan={showWorkOrder ? 8 : 7}>{emptyText}</td></tr>}
    </tbody></table></div>

    {preview && <div className="modal-backdrop archive-preview-backdrop no-print" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closePreview() }}>
      <section className="modal-card archive-preview-modal" role="dialog" aria-modal="true" aria-label={`${preview.row.archive_number} előnézete`}>
        <div className="modal-head"><div><h2>{preview.row.archive_number}</h2><p>{preview.row.original_filename}</p></div><button type="button" className="secondary" onClick={closePreview}>Bezárás</button></div>
        <div className="archive-preview-surface">
          {preview.mimeType.startsWith('image/')
            ? <img src={preview.url} alt={`${preview.row.archive_number} beszkennelt munkalap`} />
            : <iframe src={preview.url} title={`${preview.row.archive_number} PDF előnézet`} />}
        </div>
        <div className="inline-actions modal-actions"><button type="button" className="secondary" onClick={() => download(preview.row)}>Letöltés</button><button type="button" onClick={closePreview}>Bezárás</button></div>
      </section>
    </div>}

    {deleteTarget && <div className="modal-backdrop no-print" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDelete() }}>
      <section className="modal-card archive-delete-modal" role="dialog" aria-modal="true" aria-label={`${deleteTarget.archive_number} törlése`}>
        <div className="modal-head"><div><h2>Archív fájl végleges törlése</h2><p>{deleteTarget.archive_number} · {deleteTarget.original_filename}</p></div><button type="button" className="secondary" disabled={deleting} onClick={closeDelete}>Bezárás</button></div>
        <div className="warning-box archive-delete-warning"><strong>Ez a művelet nem vonható vissza.</strong><p>Az archív rekord, az eszközkapcsolatok és a feltöltött fájl is törlődik. Az esemény az auditnaplóban megmarad.</p></div>
        <form onSubmit={confirmDelete}>
          <label>A megerősítéshez gépeld be: <strong>TÖRÖL</strong><input autoFocus value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} autoComplete="off" /></label>
          <div className="inline-actions modal-actions"><button type="button" className="secondary" disabled={deleting} onClick={closeDelete}>Mégse</button><button type="submit" className="danger" disabled={deleting || deleteConfirmation !== 'TÖRÖL'}>{deleting ? 'Törlés...' : 'Végleges törlés'}</button></div>
        </form>
      </section>
    </div>}
  </>
}

function formatDate(value) { if (!value) return '—'; return new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString('hu-HU') }
function formatDateTime(value) { if (!value) return '—'; return new Date(value).toLocaleString('hu-HU') }
