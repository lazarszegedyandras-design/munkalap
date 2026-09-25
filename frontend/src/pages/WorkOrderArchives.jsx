import React, { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { api } from '../api.js'
import WorkOrderArchiveTable from '../components/WorkOrderArchiveTable.jsx'
import WorkOrderArchiveUploadModal from '../components/WorkOrderArchiveUploadModal.jsx'

const emptyPage = { items: [], page: 1, pages: 1, total: 0, page_size: 50 }

export default function WorkOrderArchives({ user }) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(emptyPage)
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [assetsLoading, setAssetsLoading] = useState(true)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')
  const canUpload = user?.role?.name !== 'Technikus / szerelő'

  useEffect(() => {
    const timeout = window.setTimeout(() => { setPage(1); setQuery(search.trim()) }, 300)
    return () => window.clearTimeout(timeout)
  }, [search])

  useEffect(() => {
    let active = true
    setAssetsLoading(true)
    api('/assets')
      .then((rows) => { if (active) setAssets(rows) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setAssetsLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    const params = new URLSearchParams({ page: String(page), page_size: '50', sort: 'created_at', order: 'desc' })
    if (query) params.set('q', query)
    api(`/work-order-archives/paged?${params.toString()}`)
      .then((result) => { if (active) setData(result) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [query, page, refreshKey])

  return <section className="work-order-archive-page">
    <div className="page-head"><div><h1>Munkalapok</h1><p className="muted">Aktív munkalapok és a korábbi nyilvántartásból archivált dokumentumok.</p></div></div>
    <nav className="work-order-subnav no-print" aria-label="Munkalap aloldalak"><NavLink to="/service/work-orders" end>Munkalapok</NavLink><NavLink to="/service/work-orders/archives">Archívum</NavLink></nav>
    <div className="archive-subpage-heading section-title-row"><div><h2>Munkalap-archívum</h2><p className="muted">Digitális munkalapokhoz és közvetlenül eszközökhöz feltöltött korábbi dokumentumok.</p></div>{canUpload && <button type="button" disabled={assetsLoading || !assets.length} onClick={() => { setSuccess(''); setUploadOpen(true) }}>{assetsLoading ? 'Eszközök betöltése...' : '+ Archív munkalap feltöltése'}</button>}</div>
    {success && <div className="success">{success}</div>}
    {error && <div className="error">{error}</div>}
    <div className="panel archive-list-controls"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Keresés archív azonosító, munkalapszám, fájlnév, eszközazonosító vagy gyári szám szerint..." /><span><strong>{data.total}</strong> találat</span></div>
    <section className="panel detail-section-card"><WorkOrderArchiveTable archives={data.items} loading={loading} showWorkOrder user={user} onDeleted={(deleted) => { setSuccess(`${deleted.archive_number} törölve.`); setRefreshKey((value) => value + 1) }} /></section>
    <div className="pagination"><button className="secondary" disabled={data.page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Előző</button><span>{data.page}. / {data.pages}. oldal</span><button className="secondary" disabled={data.page >= data.pages || loading} onClick={() => setPage((value) => value + 1)}>Következő</button></div>
    {uploadOpen && <WorkOrderArchiveUploadModal
      targetType="global"
      title="Archív munkalap feltöltése"
      assets={assets}
      onClose={() => setUploadOpen(false)}
      onSaved={(created) => {
        setUploadOpen(false)
        setSuccess(`${created.archive_number} sikeresen archiválva.`)
        setPage(1)
        setRefreshKey((value) => value + 1)
      }}
    />}
  </section>
}
