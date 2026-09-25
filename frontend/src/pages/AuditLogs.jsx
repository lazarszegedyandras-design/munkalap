import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

function formatDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('hu-HU')
}

function JsonBlock({ value }) {
  if (!value || (typeof value === 'object' && !Object.keys(value).length)) return <span className="muted">Nincs strukturált adat</span>
  return <pre className="audit-json">{JSON.stringify(value, null, 2)}</pre>
}

export default function AuditLogs() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [integrity, setIntegrity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ actor: '', entity_type: '', result: '', severity: '', correlation_id: '' })

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: '200' })
    Object.entries(filters).forEach(([key, value]) => {
      if (value.trim()) params.set(key, value.trim())
    })
    return params.toString()
  }, [filters])

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [logData, integrityData] = await Promise.all([
        api(`/audit-logs?${query}`),
        api('/audit-logs/integrity'),
      ])
      setRows(logData.items || [])
      setTotal(logData.total || 0)
      setIntegrity(integrityData)
    } catch (err) {
      setError(err.message || 'Az auditnapló nem tölthető be.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [query])

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Auditnapló</h1>
          <p className="muted">Strukturált, append-only eseménynapló szereplő-, kérés- és integritási adatokkal.</p>
        </div>
        <button className="secondary" onClick={load}>Frissítés</button>
      </div>

      {integrity && (
        <div className={`panel audit-integrity ${integrity.valid ? 'audit-integrity-ok' : 'audit-integrity-bad'}`}>
          <strong>{integrity.valid ? 'Hash-chain: rendben' : 'Hash-chain: HIBA'}</strong>
          <span>Ellenőrzött rekordok: {integrity.checked_count} / {integrity.total_count}</span>
          {!integrity.valid && <span>Hibás rekord: {integrity.broken_audit_id || 'láncállapot'} · {integrity.reason}</span>}
          {integrity.chain_head && <code title={integrity.chain_head}>Fej: {integrity.chain_head.slice(0, 16)}…</code>}
        </div>
      )}

      <div className="panel">
        <h2>Szűrés</h2>
        <div className="audit-filter-grid">
          <label>Felhasználó<input value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} placeholder="név vagy e-mail" /></label>
          <label>Objektumtípus<input value={filters.entity_type} onChange={(e) => setFilters({ ...filters, entity_type: e.target.value })} placeholder="pl. work_order" /></label>
          <label>Eredmény<select value={filters.result} onChange={(e) => setFilters({ ...filters, result: e.target.value })}><option value="">Mind</option><option value="success">Sikeres</option><option value="failure">Sikertelen</option></select></label>
          <label>Súlyosság<select value={filters.severity} onChange={(e) => setFilters({ ...filters, severity: e.target.value })}><option value="">Mind</option><option value="info">Info</option><option value="warning">Figyelmeztetés</option><option value="error">Hiba</option></select></label>
          <label>Correlation ID<input value={filters.correlation_id} onChange={(e) => setFilters({ ...filters, correlation_id: e.target.value })} /></label>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {loading ? <div className="center">Betöltés...</div> : (
        <div className="panel">
          <div className="panel-head"><h2>Események</h2><span className="muted">{total} találat · legfeljebb 200 rekord látható</span></div>
          <div className="audit-list">
            {rows.map((row) => (
              <details className={`audit-row audit-${row.result}`} key={row.id}>
                <summary>
                  <span className="audit-time">{formatDateTime(row.created_at)}</span>
                  <strong>{row.action}</strong>
                  <span>{row.actor_name || row.actor_email || 'Rendszer / ismeretlen'}</span>
                  <span>{row.entity_type} · {row.entity_display_id || row.entity_id}</span>
                  <span className={`audit-result-pill ${row.result}`}>{row.result === 'success' ? 'sikeres' : 'sikertelen'}</span>
                </summary>
                <div className="audit-detail-grid">
                  <div><b>Leírás</b><p>{row.description}</p></div>
                  <div><b>Szereplő snapshot</b><p>{[row.actor_name, row.actor_email, row.actor_role].filter(Boolean).join(' · ') || 'Nincs'}</p></div>
                  <div><b>Request ID</b><code>{row.request_id || ''}</code></div>
                  <div><b>Correlation ID</b><code>{row.correlation_id || ''}</code></div>
                  <div><b>Session ID</b><code>{row.session_id || ''}</code></div>
                  <div><b>IP</b><code>{row.ip_address || ''}</code></div>
                  <div className="audit-wide"><b>User-Agent</b><code>{row.user_agent || ''}</code></div>
                  <div><b>Súlyosság</b><p>{row.severity}</p></div>
                  <div><b>Hash</b><code title={row.entry_hash}>{row.entry_hash}</code></div>
                </div>
                <div className="audit-state-grid">
                  <div><h3>Változások</h3><JsonBlock value={row.changes} /></div>
                  <div><h3>Előtte</h3><JsonBlock value={row.before_data} /></div>
                  <div><h3>Utána</h3><JsonBlock value={row.after_data} /></div>
                </div>
              </details>
            ))}
            {!rows.length && <p className="muted">Nincs a szűrésnek megfelelő auditbejegyzés.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
