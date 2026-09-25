import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'

const STATUS_LABELS = {
  pending: 'Jóváhagyásra vár',
  approved: 'Jóváhagyva',
  rejected: 'Elutasítva',
  withdrawn: 'Visszavonva',
}

function money(value, currency = 'HUF') {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '–'
  try { return new Intl.NumberFormat('hu-HU', { style: 'currency', currency, maximumFractionDigits: 2 }).format(amount) }
  catch { return `${amount.toLocaleString('hu-HU')} ${currency}` }
}

function when(value) { return value ? new Date(value).toLocaleString('hu-HU') : '–' }

export default function ProcurementRequests() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const query = new URLSearchParams({ page_size: '100' })
      if (search.trim()) query.set('search', search.trim())
      if (status) query.set('status', status)
      const data = await api(`/procurement/requests?${query}`)
      setRows(data.items || [])
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [status])

  return (
    <section className="procurement-page">
      <div className="page-head">
        <div><h1>Beszerzési igényeim</h1><p className="muted">Saját beszerzési igények és azok aktuális jóváhagyási állapota.</p></div>
        <button onClick={() => navigate('/procurement/new')}>Új beszerzési igény</button>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="panel procurement-filter-panel">
        <div className="filters procurement-filters">
          <label>Keresés<input value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} placeholder="Azonosító, tárgy vagy cél" /></label>
          <label>Státusz<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Mind</option>{Object.entries(STATUS_LABELS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
          <div className="form-actions"><button type="button" onClick={load}>Szűrés</button></div>
        </div>
      </div>
      {loading ? <div className="panel">Betöltés...</div> : rows.length ? (
        <DataTable
          rows={rows}
          onRowClick={(row) => navigate(`/procurement/requests/${row.id}`)}
          columns={[
            { key: 'request_number', label: 'Azonosító' },
            { key: 'subject', label: 'Tárgy' },
            { key: 'total_amount', label: 'Összérték', render: row => money(row.total_amount, row.currency) },
            { key: 'status', label: 'Státusz', render: row => <span className={`procurement-status status-${row.status}`}>{STATUS_LABELS[row.status] || row.status}</span> },
            { key: 'submitted_at', label: 'Beküldés', render: row => when(row.submitted_at) },
            { key: 'approver.full_name', label: 'Jóváhagyó', render: row => row.approver?.full_name || '–' },
          ]}
        />
      ) : <div className="panel">Nincs a szűrésnek megfelelő beszerzési igény.</div>}
    </section>
  )
}
