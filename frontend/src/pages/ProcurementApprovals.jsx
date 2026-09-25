import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'

const STATUS_LABELS = { pending: 'Jóváhagyásra vár', approved: 'Jóváhagyva', rejected: 'Elutasítva', withdrawn: 'Visszavonva' }
function money(value, currency = 'HUF') { const amount = Number(value); try { return new Intl.NumberFormat('hu-HU', { style: 'currency', currency, maximumFractionDigits: 2 }).format(amount) } catch { return `${amount.toLocaleString('hu-HU')} ${currency}` } }
function when(value) { return value ? new Date(value).toLocaleString('hu-HU') : '–' }

export default function ProcurementApprovals() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('pending')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const query = new URLSearchParams({ page_size: '100', status })
      if (search.trim()) query.set('search', search.trim())
      if (dateFrom) query.set('date_from', dateFrom)
      if (dateTo) query.set('date_to', dateTo)
      const data = await api(`/procurement/approvals?${query}`)
      setRows(data.items || [])
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [status])

  return (
    <section className="procurement-page">
      <div className="page-head"><div><h1>Beszerzési jóváhagyások</h1><p className="muted">Függő és korábbi beszerzési igények áttekintése.</p></div></div>
      {error && <div className="error">{error}</div>}
      <div className="panel">
        <div className="procurement-tabs">{[['pending','Jóváhagyásra vár'],['','Korábbi / összes'],['approved','Jóváhagyott'],['rejected','Elutasított'],['withdrawn','Visszavont']].map(([key,label]) => <button type="button" key={label} className={status === key ? '' : 'secondary'} onClick={() => setStatus(key)}>{label}</button>)}</div>
        <div className="filters procurement-filters">
          <label>Keresés<input value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} placeholder="Kérelmező, azonosító, tárgy" /></label>
          <label>Dátumtól<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
          <label>Dátumig<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
          <div className="form-actions"><button type="button" onClick={load}>Szűrés</button></div>
        </div>
      </div>
      {loading ? <div className="panel">Betöltés...</div> : rows.length ? <DataTable rows={rows} onRowClick={(row) => navigate(`/procurement/requests/${row.id}`)} columns={[
        { key: 'request_number', label: 'Azonosító' },
        { key: 'requester.full_name', label: 'Kérelmező' },
        { key: 'subject', label: 'Tárgy' },
        { key: 'total_amount', label: 'Összeg', render: row => money(row.total_amount, row.currency) },
        { key: 'status', label: 'Státusz', render: row => <span className={`procurement-status status-${row.status}`}>{STATUS_LABELS[row.status] || row.status}</span> },
        { key: 'submitted_at', label: 'Dátum', render: row => when(row.submitted_at) },
      ]} /> : <div className="panel">Nincs a szűrésnek megfelelő beszerzési igény.</div>}
    </section>
  )
}
