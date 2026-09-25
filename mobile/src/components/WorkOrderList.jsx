import { formatTime } from '../services/format.js'
export default function WorkOrderList({ orders, onOpen, onRefresh, loading, me, onLogout }) {
  return <main>
    <header className="app-header"><div><strong>Munkalap</strong><small>{me?.full_name}</small></div><button className="icon-btn" onClick={onLogout}>Kilépés</button></header>
    <section className="page"><div className="page-title-row"><div><h1>Mai munkáim</h1><p>{new Intl.DateTimeFormat('hu-HU', { dateStyle: 'full' }).format(new Date())}</p></div><button className="btn secondary small" onClick={onRefresh} disabled={loading}>Frissítés</button></div>
      {loading && <div className="notice">Betöltés…</div>}
      {!loading && !orders.length && <div className="empty-card">Mára nincs hozzád rendelt munkalap.</div>}
      <div className="order-list">{orders.map(order => <button key={order.id} className="order-card" onClick={() => onOpen(order.id)}>
        <div className="order-time">{formatTime(order.planned_start_at)}</div>
        <div className="order-main"><strong>{order.customer_name || 'Ügyfél nélkül'}</strong><span>{order.location_name || order.location_address || order.customer_address || '–'}</span><span>{order.assets?.map(a => a.display_name).join(', ') || 'Nincs eszköz'}</span><div className="badges"><em>{order.status}</em><em>{order.number}</em></div></div><span className="chevron">›</span>
      </button>)}</div>
    </section>
  </main>
}
