import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

const moduleLabels = { service: 'Szerviz', hr: 'HR', crm: 'CRM', admin: 'Admin' }
const fmt = (value) => value ? new Date(value).toLocaleString('hu-HU') : ''

export default function Notifications() {
  const [rows, setRows] = useState([])
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  async function load() { try { setRows(await api(`/notifications?unread_only=${unreadOnly ? 'true' : 'false'}&limit=100`)); setError('') } catch (e) { setError(e.message) } }
  useEffect(() => { load() }, [unreadOnly])
  async function open(row) {
    if (!row.is_read) await api(`/notifications/${row.id}/read`, { method: 'POST' })
    window.dispatchEvent(new CustomEvent('app:notifications-changed'))
    if (row.link) navigate(row.link)
    else load()
  }
  async function readAll() { await api('/notifications/read-all', { method: 'POST' }); window.dispatchEvent(new CustomEvent('app:notifications-changed')); await load() }
  return <section>
    <div className="page-head"><div><h1>Értesítések</h1><p className="muted">HR-jóváhagyások, CRM-határidők, lejáró szerződések és saját tervezett munkalapok.</p></div><div className="inline-actions"><label className="checkbox"><input type="checkbox" checked={unreadOnly} onChange={e=>setUnreadOnly(e.target.checked)} /> Csak olvasatlan</label><button className="secondary" onClick={readAll}>Mind olvasottnak</button></div></div>
    {error && <div className="error">{error}</div>}
    <div className="notification-list">{rows.map(row => <button key={row.id} className={`notification-row ${row.is_read ? 'read' : 'unread'}`} onClick={()=>open(row)}>
      <span className="notification-module">{moduleLabels[row.module] || row.module}</span>
      <span className="notification-body"><strong>{row.title}</strong><span>{row.message || ''}</span></span>
      <time>{fmt(row.created_at)}</time>
    </button>)}</div>
    {!rows.length && <div className="panel muted">Nincs megjeleníthető értesítés.</div>}
  </section>
}
