import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { Field } from '../components/FormField.jsx'
import AssetQuickMeterModal from '../components/AssetQuickMeterModal.jsx'
import WorkOrderArchiveTable from '../components/WorkOrderArchiveTable.jsx'
import WorkOrderArchiveUploadModal from '../components/WorkOrderArchiveUploadModal.jsx'
import { assetLabel, visibleInternalId } from '../utils/assets.js'
import { StatusBadge } from './Assets.jsx'

const emptyComponent = { name: '', part_number: '', expected_life_pages: '', last_replacement_at: '', last_replacement_meter: '', note: '' }
const emptyReplacement = { asset_component_id: '', meter_value: '', replaced_at: '', material_id: '', work_order_id: '', note: '' }
const tabs = [
  ['overview', 'Áttekintés'],
  ['tracking', 'Számláló és alkatrészek'],
  ['work-orders', 'Munkalapok'],
  ['history', 'Történet'],
  ['master-data', 'Törzsadatok'],
]

export default function AssetDetail({ user }) {
  const { assetId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = tabs.some(([key]) => key === searchParams.get('tab')) ? searchParams.get('tab') : 'overview'
  const [asset, setAsset] = useState(null)
  const [tracking, setTracking] = useState(null)
  const [workOrders, setWorkOrders] = useState([])
  const [archives, setArchives] = useState([])
  const [history, setHistory] = useState([])
  const [materials, setMaterials] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [quickMeterOpen, setQuickMeterOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)
  const canEdit = ['Admin', 'Irodai felhasználó'].includes(user?.role?.name)
  const canDelete = user?.role?.name === 'Admin'

  async function loadAll() {
    setLoading(true)
    setError('')
    try {
      const [assetRow, trackingData, orders, archiveRows, historyRows, materialRows] = await Promise.all([
        api(`/assets/${assetId}`),
        api(`/assets/${assetId}/printer-tracking`),
        api(`/assets/${assetId}/work-orders`),
        api(`/assets/${assetId}/work-order-archives`),
        api(`/assets/${assetId}/history`),
        api('/materials'),
      ])
      setAsset(assetRow)
      setTracking(trackingData)
      setWorkOrders(orders)
      setArchives(archiveRows)
      setHistory(historyRows)
      setMaterials(materialRows)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [assetId])
  useEffect(() => {
    function close(event) { if (!menuRef.current?.contains(event.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  function selectTab(key) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (key === 'overview') next.delete('tab')
      else next.set('tab', key)
      return next
    }, { replace: true })
  }

  async function remove() {
    setMenuOpen(false)
    if (!confirm(`Biztosan törlöd ezt az eszközt?\n\n${assetLabel(asset)}`)) return
    try {
      await api(`/assets/${asset.id}`, { method: 'DELETE' })
      navigate('/assets')
    } catch (err) { setError(err.message) }
  }

  if (loading) return <div className="panel">Eszközadatok betöltése...</div>
  if (error && !asset) return <><div className="error">{error}</div><Link className="button secondary" to="/assets">Vissza az eszközökhöz</Link></>

  const activeComponents = (tracking?.components || []).filter((component) => component.is_active)
  const urgentComponents = activeComponents.filter((component) => ['overdue', 'due_30_days'].includes(component.forecast_status))

  return (
    <section className="asset-detail-page">
      <Link className="breadcrumb" to="/assets">← Vissza az eszközlistához</Link>
      {error && <div className="error">{error}</div>}
      <div className="asset-detail-header panel">
        <div className="asset-detail-title">
          <div className="asset-title-line">
            <h1>{asset.display_name || assetLabel(asset)}</h1>
            <StatusBadge status={asset.status} />
            <span className="company-code-badge large">{asset.company_code || 'Nincs cégkód'}</span>
          </div>
          <p>{asset.serial_number ? `Gyári szám: ${asset.serial_number}` : 'Nincs gyári szám'} · {asset.customer_name || (asset.internal_use ? 'Belső használat' : 'Nincs ügyfél')} · {asset.location_name || 'Nincs helyszín'}</p>
        </div>
        <div className="asset-detail-actions" ref={menuRef}>
          <button type="button" onClick={() => navigate(`/work-orders/new?new_asset_id=${asset.id}`)}>+ Új munkalap</button>
          {canEdit && <Link className="button secondary" to={`/assets/${asset.id}/edit`}>Szerkesztés</Link>}
          <button type="button" className="icon-button menu-trigger" aria-label="További műveletek" onClick={() => setMenuOpen((value) => !value)}>⋮</button>
          {menuOpen && <div className="row-action-menu detail-menu">
            <button type="button" onClick={() => { setMenuOpen(false); setQuickMeterOpen(true) }}>Számláló rögzítése</button>
            <button type="button" onClick={() => { setMenuOpen(false); selectTab('tracking') }}>Alkatrészcsere</button>
            {canDelete && <><div className="menu-separator" /><button type="button" className="danger-text" onClick={remove}>Törlés</button></>}
          </div>}
        </div>
      </div>

      <AssetAlerts asset={asset} tracking={tracking} urgentComponents={urgentComponents} />

      <div className="asset-tabs" role="tablist" aria-label="Eszközadatlap fülek">
        {tabs.map(([key, label]) => <button type="button" role="tab" aria-selected={activeTab === key} className={activeTab === key ? 'active' : ''} key={key} onClick={() => selectTab(key)}>{label}{key === 'tracking' && urgentComponents.length ? <span className="tab-count">{urgentComponents.length}</span> : ''}</button>)}
      </div>

      {activeTab === 'overview' && <OverviewTab asset={asset} tracking={tracking} workOrders={workOrders} onQuickMeter={() => setQuickMeterOpen(true)} onTracking={() => selectTab('tracking')} onNewWorkOrder={() => navigate(`/work-orders/new?new_asset_id=${asset.id}`)} onOpenWorkOrder={(id) => navigate(`/work-orders/${id}`)} />}
      {activeTab === 'tracking' && <TrackingTab asset={asset} data={tracking} workOrders={workOrders} materials={materials} canManageComponents={canEdit} onChanged={setTracking} onError={setError} />}
      {activeTab === 'work-orders' && <WorkOrdersTab asset={asset} workOrders={workOrders} archives={archives} canArchive={canEdit} user={user} navigate={navigate} onArchiveAdded={(created) => setArchives((rows) => [created, ...rows])} onArchiveDeleted={(deleted) => setArchives((rows) => rows.filter((row) => row.id !== deleted.id))} />}
      {activeTab === 'history' && <HistoryTab history={history} />}
      {activeTab === 'master-data' && <MasterDataTab asset={asset} />}

      {quickMeterOpen && <AssetQuickMeterModal asset={asset} onClose={() => setQuickMeterOpen(false)} onSaved={(data) => setTracking(data)} />}
    </section>
  )
}

function AssetAlerts({ asset, tracking, urgentComponents }) {
  const alerts = []
  if (tracking?.meter_is_stale) alerts.push(tracking.latest_meter ? `Az utolsó számlálóállás ${tracking.meter_age_days} napos.` : 'Még nincs rögzített számlálóállás.')
  urgentComponents.forEach((component) => alerts.push(`${component.name}: ${component.forecast_status_label}${component.forecast_at ? ` (${formatDate(component.forecast_at)})` : ''}.`))
  const maintenanceDate = asset.effective_next_maintenance_date || asset.next_maintenance_date
  if (asset.maintenance_state === 'missing_last') {
    alerts.push(`A szerződéses ciklus ${asset.maintenance_cycle_label || 'meg van adva'}, de az utolsó karbantartás dátuma hiányzik.`)
  } else if (maintenanceDate) {
    const days = daysUntil(maintenanceDate)
    if (days <= 30) alerts.push(days < 0 ? `A karbantartás ${Math.abs(days)} napja lejárt.` : `Karbantartás ${days === 0 ? 'ma' : `${days} napon belül`} esedékes.`)
  }
  if (!alerts.length) return null
  return <div className="asset-alert-list">{alerts.map((message, index) => <div className="asset-alert" key={`${message}-${index}`}>⚠ {message}</div>)}</div>
}

function OverviewTab({ asset, tracking, workOrders, onQuickMeter, onTracking, onNewWorkOrder, onOpenWorkOrder }) {
  const activeComponents = (tracking?.components || []).filter((component) => component.is_active)
  const nextComponent = activeComponents.filter((component) => component.forecast_at).sort((a, b) => new Date(a.forecast_at) - new Date(b.forecast_at))[0]
  const lastOrder = workOrders[0]
  return <div className="asset-overview-layout">
    <div className="asset-overview-main">
      <div className="asset-overview-metrics">
        <OverviewMetric label="Aktuális számlálók" value={tracking?.latest_meter ? meterSummary(tracking.latest_meter) : 'Nincs adat'} />
        <OverviewMetric label="Átlagos havi használat" value={tracking?.average_monthly_usage !== null && tracking?.average_monthly_usage !== undefined ? `${formatNumber(tracking.average_monthly_usage)} oldal/hó` : 'Nincs elegendő adat'} />
        <OverviewMetric label="Utolsó karbantartás" value={asset.last_maintenance_date ? `${formatDate(asset.last_maintenance_date)}${asset.maintenance_days_since_last != null ? ` · ${asset.maintenance_days_since_last} napja` : ''}` : 'Nincs adat'} warning={!asset.last_maintenance_date} />
        <OverviewMetric label="Szerződéses ciklus" value={asset.maintenance_cycle_label || 'Nincs megadva'} warning={!asset.maintenance_cycle_label} />
        <OverviewMetric label="Következő karbantartás" value={formatDate(asset.effective_next_maintenance_date || asset.next_maintenance_date)} warning={['overdue', 'due_30_days', 'missing_last'].includes(asset.maintenance_state)} />
        <OverviewMetric label="Következő alkatrészcsere" value={nextComponent ? `${nextComponent.name} · ${formatDate(nextComponent.forecast_at)}` : 'Nincs előrejelzés'} />
      </div>
      <section className="panel detail-section-card">
        <h2>Elhelyezés és felelősség</h2>
        <div className="detail-definition-grid">
          <Definition label="Cégkód" value={asset.company_code} />
          <Definition label="Ügyfél" value={asset.customer_name || (asset.internal_use ? 'Belső használat' : null)} />
          <Definition label="Helyszín" value={asset.location_name} />
          <Definition label="Állapot" value={asset.status} />
        </div>
      </section>
      <section className="panel detail-section-card">
        <h2>Utolsó munkalap</h2>
        {lastOrder ? <button type="button" className="work-order-summary-card" onClick={() => onOpenWorkOrder(lastOrder.id)}><strong>{lastOrder.number}</strong><span>{lastOrder.description}</span><small>{lastOrder.status} · {lastOrder.technician_name || 'nincs technikus'} · {formatDate(lastOrder.planned_date || lastOrder.created_at)}</small></button> : <p className="muted">Még nincs ehhez az eszközhöz kapcsolódó munkalap.</p>}
      </section>
    </div>
    <aside className="panel asset-quick-actions">
      <h2>Gyorsműveletek</h2>
      <button type="button" onClick={onQuickMeter}>Számláló rögzítése</button>
      <button type="button" className="secondary" onClick={onTracking}>Alkatrészek és cserék</button>
      <button type="button" className="secondary" onClick={onNewWorkOrder}>Új munkalap</button>
    </aside>
  </div>
}

function TrackingTab({ asset, data, workOrders, materials, canManageComponents, onChanged, onError }) {
  const [componentForm, setComponentForm] = useState(emptyComponent)
  const [replacementForm, setReplacementForm] = useState({ ...emptyReplacement, meter_value: data?.latest_meter?.value ?? '' })
  const [showComponentForm, setShowComponentForm] = useState(false)
  const [showReplacementForm, setShowReplacementForm] = useState(false)
  const activeComponents = (data?.components || []).filter((component) => component.is_active)

  useEffect(() => { setReplacementForm((previous) => ({ ...previous, meter_value: data?.latest_meter?.value ?? '' })) }, [data?.latest_meter?.value])

  async function saveComponent(event) {
    event.preventDefault(); onError('')
    try {
      const updated = await api(`/assets/${asset.id}/components`, { method: 'POST', body: {
        name: componentForm.name,
        part_number: componentForm.part_number || null,
        expected_life_pages: componentForm.expected_life_pages ? Number(componentForm.expected_life_pages) : null,
        last_replacement_at: componentForm.last_replacement_at || null,
        last_replacement_meter: componentForm.last_replacement_meter ? Number(componentForm.last_replacement_meter) : null,
        note: componentForm.note || null,
      } })
      onChanged(updated); setComponentForm(emptyComponent); setShowComponentForm(false)
    } catch (err) { onError(err.message) }
  }

  async function saveReplacement(event) {
    event.preventDefault(); onError('')
    try {
      const updated = await api(`/assets/${asset.id}/component-replacements`, { method: 'POST', body: {
        asset_component_id: Number(replacementForm.asset_component_id),
        meter_value: Number(replacementForm.meter_value),
        replaced_at: replacementForm.replaced_at || null,
        material_id: replacementForm.material_id ? Number(replacementForm.material_id) : null,
        work_order_id: replacementForm.work_order_id ? Number(replacementForm.work_order_id) : null,
        note: replacementForm.note || null,
      } })
      onChanged(updated); setReplacementForm({ ...emptyReplacement, meter_value: updated.latest_meter?.value ?? '' }); setShowReplacementForm(false)
    } catch (err) { onError(err.message) }
  }

  async function deleteReading(id) {
    if (!confirm('Törlöd ezt a számlálóállást?')) return
    try { await api(`/assets/${asset.id}/meter-readings/${id}`, { method: 'DELETE' }); onChanged(await api(`/assets/${asset.id}/printer-tracking`)) } catch (err) { onError(err.message) }
  }
  async function deleteComponent(id) {
    if (!confirm('Törlöd vagy inaktiválod ezt az alkatrészt?')) return
    try { await api(`/assets/${asset.id}/components/${id}`, { method: 'DELETE' }); onChanged(await api(`/assets/${asset.id}/printer-tracking`)) } catch (err) { onError(err.message) }
  }

  return <div className="asset-tracking-tab">
    <div className="asset-overview-metrics">
      <OverviewMetric label="Aktuális számlálók" value={data?.latest_meter ? meterSummary(data.latest_meter) : 'Nincs adat'} />
      <OverviewMetric label="Utolsó mérés" value={data?.latest_meter ? formatDateTime(data.latest_meter.recorded_at) : 'Nincs adat'} warning={data?.meter_is_stale} />
      <OverviewMetric label="Havi átlag" value={data?.average_monthly_usage !== null && data?.average_monthly_usage !== undefined ? `${formatNumber(data.average_monthly_usage)} oldal/hó` : 'Nincs elegendő adat'} />
      <OverviewMetric label="Követett alkatrészek" value={String(activeComponents.length)} />
    </div>

    <section className="panel detail-section-card">
      <div className="section-heading-actions"><div><h2>Alkatrészek és előrejelzés</h2><p className="muted">Élettartam, felhasználás és várható csere.</p></div><div className="form-actions">{canManageComponents && <button type="button" className="secondary" onClick={() => setShowComponentForm((value) => !value)}>+ Alkatrész</button>}<button type="button" onClick={() => setShowReplacementForm((value) => !value)}>+ Csere rögzítése</button></div></div>
      {showComponentForm && canManageComponents && <form className="inline-editor grid-form" onSubmit={saveComponent}>
        <Field label="Megnevezés"><input required value={componentForm.name} onChange={(event) => setComponentForm({ ...componentForm, name: event.target.value })} /></Field>
        <Field label="Cikkszám"><input value={componentForm.part_number} onChange={(event) => setComponentForm({ ...componentForm, part_number: event.target.value })} /></Field>
        <Field label="Élettartam (oldal)"><input type="number" min="1" value={componentForm.expected_life_pages} onChange={(event) => setComponentForm({ ...componentForm, expected_life_pages: event.target.value })} /></Field>
        <Field label="Utolsó csere"><input type="datetime-local" value={componentForm.last_replacement_at} onChange={(event) => setComponentForm({ ...componentForm, last_replacement_at: event.target.value })} /></Field>
        <Field label="Cserekori számláló"><input type="number" min="0" value={componentForm.last_replacement_meter} onChange={(event) => setComponentForm({ ...componentForm, last_replacement_meter: event.target.value })} /></Field>
        <Field label="Megjegyzés"><input value={componentForm.note} onChange={(event) => setComponentForm({ ...componentForm, note: event.target.value })} /></Field>
        <div className="form-actions"><button>Mentés</button><button type="button" className="secondary" onClick={() => setShowComponentForm(false)}>Mégse</button></div>
      </form>}
      {showReplacementForm && <form className="inline-editor grid-form" onSubmit={saveReplacement}>
        <Field label="Alkatrész"><select required value={replacementForm.asset_component_id} onChange={(event) => setReplacementForm({ ...replacementForm, asset_component_id: event.target.value })}><option value="">Válassz</option>{activeComponents.map((component) => <option value={component.id} key={component.id}>{component.name}{component.part_number ? ` (${component.part_number})` : ''}</option>)}</select></Field>
        <Field label="Cserekori számláló"><input required type="number" min="0" value={replacementForm.meter_value} onChange={(event) => setReplacementForm({ ...replacementForm, meter_value: event.target.value })} /></Field>
        <Field label="Csere időpontja"><input type="datetime-local" value={replacementForm.replaced_at} onChange={(event) => setReplacementForm({ ...replacementForm, replaced_at: event.target.value })} /></Field>
        <Field label="Felhasznált anyag"><select value={replacementForm.material_id} onChange={(event) => setReplacementForm({ ...replacementForm, material_id: event.target.value })}><option value="">Nincs megadva</option>{materials.map((material) => <option value={material.id} key={material.id}>{material.sku} – {material.name}</option>)}</select></Field>
        <Field label="Kapcsolódó munkalap"><select value={replacementForm.work_order_id} onChange={(event) => setReplacementForm({ ...replacementForm, work_order_id: event.target.value })}><option value="">Nincs</option>{workOrders.map((order) => <option value={order.id} key={order.id}>{order.number} – {order.description}</option>)}</select></Field>
        <Field label="Megjegyzés"><input value={replacementForm.note} onChange={(event) => setReplacementForm({ ...replacementForm, note: event.target.value })} /></Field>
        <div className="form-actions"><button disabled={!activeComponents.length}>Csere rögzítése</button><button type="button" className="secondary" onClick={() => setShowReplacementForm(false)}>Mégse</button></div>
      </form>}
      <div className="mini-table-wrap"><table className="mini-table printer-table"><thead><tr><th>Alkatrész</th><th>Élettartam</th><th>Utolsó csere</th><th>Felhasználás</th><th>Hátralévő oldal</th><th>Várható csere</th><th>Állapot</th>{canManageComponents && <th></th>}</tr></thead><tbody>
        {data?.components?.length ? data.components.map((component) => <tr key={component.id} className={!component.is_active ? 'inactive-row' : ''}><td><strong>{component.name}</strong>{component.part_number && <small>{component.part_number}</small>}</td><td>{formatInteger(component.expected_life_pages)}</td><td>{formatDateTime(component.last_replacement_at)}<small>{component.last_replacement_meter !== null ? `${formatInteger(component.last_replacement_meter)} oldal` : ''}</small></td><td>{component.usage_percent !== null ? `${formatNumber(component.usage_percent)}%` : '—'}</td><td>{formatInteger(component.remaining_pages)}</td><td>{formatDate(component.forecast_at)}</td><td><ForecastBadge component={component} /></td>{canManageComponents && <td><button type="button" className="danger small-button" onClick={() => deleteComponent(component.id)}>{component.is_active ? 'Inaktiválás' : 'Törlés'}</button></td>}</tr>) : <tr><td colSpan={canManageComponents ? 8 : 7}>Nincs követett alkatrész.</td></tr>}
      </tbody></table></div>
    </section>

    <section className="panel detail-section-card">
      <h2>Számlálóelőzmények</h2>
      <div className="mini-table-wrap"><table className="mini-table"><thead><tr><th>Időpont</th><th>Összes</th><th>FF</th><th>Színes</th><th>Scan</th><th>Munkalap</th><th>Rögzítő</th><th>Megjegyzés</th>{canManageComponents && <th></th>}</tr></thead><tbody>
        {data?.readings?.length ? data.readings.map((reading) => <tr key={reading.id}><td>{formatDateTime(reading.recorded_at)}</td><td>{formatInteger(reading.value)}</td><td>{formatInteger(reading.black_white_value)}</td><td>{formatInteger(reading.color_value)}</td><td>{formatInteger(reading.scan_value)}</td><td>{reading.work_order_number || '—'}</td><td>{reading.recorded_by_name || '—'}</td><td>{reading.note || '—'}</td>{canManageComponents && <td><button type="button" className="danger small-button" onClick={() => deleteReading(reading.id)}>Törlés</button></td>}</tr>) : <tr><td colSpan={canManageComponents ? 9 : 8}>Nincs számlálóállás.</td></tr>}
      </tbody></table></div>
    </section>

    <section className="panel detail-section-card">
      <h2>Csereelőzmények</h2>
      <div className="mini-table-wrap"><table className="mini-table"><thead><tr><th>Időpont</th><th>Alkatrész</th><th>Számláló</th><th>Anyag</th><th>Munkalap</th><th>Technikus</th><th>Megjegyzés</th></tr></thead><tbody>
        {data?.replacements?.length ? data.replacements.map((replacement) => <tr key={replacement.id}><td>{formatDateTime(replacement.replaced_at)}</td><td>{replacement.component_name}</td><td>{formatInteger(replacement.meter_value)}</td><td>{replacement.material_sku ? `${replacement.material_sku} – ${replacement.material_name}` : '—'}</td><td>{replacement.work_order_number || '—'}</td><td>{replacement.technician_name || '—'}</td><td>{replacement.note || '—'}</td></tr>) : <tr><td colSpan="7">Nincs rögzített alkatrészcsere.</td></tr>}
      </tbody></table></div>
    </section>
  </div>
}

function meterSummary(reading) {
  const parts = [`Összes: ${formatInteger(reading.value)}`]
  if (reading.black_white_value !== null && reading.black_white_value !== undefined) parts.push(`FF: ${formatInteger(reading.black_white_value)}`)
  if (reading.color_value !== null && reading.color_value !== undefined) parts.push(`Színes: ${formatInteger(reading.color_value)}`)
  if (reading.scan_value !== null && reading.scan_value !== undefined) parts.push(`Scan: ${formatInteger(reading.scan_value)}`)
  return parts.join(' · ')
}

function WorkOrdersTab({ asset, workOrders, archives, canArchive, user, navigate, onArchiveAdded, onArchiveDeleted }) {
  const [uploadOpen, setUploadOpen] = useState(false)
  const ordered = [...workOrders].sort((a, b) => new Date(b.completed_at || b.planned_start_at || b.planned_date || b.created_at) - new Date(a.completed_at || a.planned_start_at || a.planned_date || a.created_at))
  return <div className="asset-work-order-sections">
    <section className="panel detail-section-card">
      <div className="section-heading-actions"><div><h2>Archivált munkalapok</h2><p className="muted">Digitális munkalaphoz kapcsolt fájlok és a korábbi nyilvántartás közvetlenül ehhez az eszközhöz feltöltött dokumentumai.</p></div>{canArchive && <button type="button" onClick={() => setUploadOpen(true)}>Korábbi munkalap archiválása</button>}</div>
      <WorkOrderArchiveTable archives={archives} showWorkOrder emptyText="Ehhez az eszközhöz még nincs közvetlenül archivált vagy munkalapról kapcsolt fájl." user={user} onDeleted={onArchiveDeleted} />
    </section>
    <section className="panel detail-section-card">
      <div className="section-heading-actions"><div><h2>Kapcsolódó digitális munkalapok</h2><p className="muted">{ordered.length} munkalap · kattints a részletek megnyitásához.</p></div></div>
      <div className="mini-table-wrap"><table className="mini-table clickable-table compact-work-order-table"><thead><tr><th>Munkalap</th><th>Időpont</th><th>Státusz</th><th>Munka típusa</th><th>Technikus</th><th>Feladat</th></tr></thead><tbody>{ordered.length ? ordered.map((order) => <tr key={order.id} tabIndex="0" onClick={() => navigate(`/work-orders/${order.id}`)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') navigate(`/work-orders/${order.id}`) }}>
        <td><strong>{order.number}</strong><small className="cell-subline">{order.priority || 'normál'} prioritás</small></td>
        <td>{formatDate(order.completed_at || order.planned_start_at || order.planned_date || order.created_at)}</td>
        <td><WorkOrderStatusBadge status={order.status} /></td>
        <td>{order.work_type || '—'}</td>
        <td>{workOrderTechnicians(order)}</td>
        <td><span className="compact-description" title={order.description}>{order.description}</span></td>
      </tr>) : <tr><td colSpan="6">Nincs kapcsolódó munkalap.</td></tr>}</tbody></table></div>
    </section>
    {uploadOpen && <WorkOrderArchiveUploadModal targetType="asset" targetId={asset.id} title={`Korábbi munkalap archiválása – ${asset.display_name || assetLabel(asset)}`} onClose={() => setUploadOpen(false)} onSaved={(created) => { onArchiveAdded(created); setUploadOpen(false) }} />}
  </div>
}

function workOrderTechnicians(order) {
  const names = order?.technician_names?.length
    ? order.technician_names
    : [order?.technician_name, order?.secondary_technician_name].filter(Boolean)
  return names.length ? names.join(', ') : 'Nincs kijelölve'
}

function WorkOrderStatusBadge({ status }) {
  const css = String(status || '').replaceAll(' ', '-').replaceAll('/', '-').replaceAll('ő', 'o').replaceAll('á', 'a').replaceAll('é', 'e')
  return <span className={`work-order-status-badge status-${css}`}>{status || '—'}</span>
}

function HistoryTab({ history }) {
  return <section className="panel detail-section-card"><h2>Eszköztörténet</h2>{history.length ? <div className="asset-timeline">{history.map((item) => <div className="asset-timeline-item" key={item.id}><div className="timeline-dot" /><div><strong>{item.action}</strong><p>{item.description}</p><small>{formatDateTime(item.changed_at)}{item.user_name ? ` · ${item.user_name}` : ''}{item.work_order_number ? ` · ${item.work_order_number}` : ''}</small></div></div>)}</div> : <p className="muted">Nincs naplózott eszköztörténet.</p>}</section>
}

function MasterDataTab({ asset }) {
  return <section className="panel detail-section-card"><h2>Törzsadatok</h2><div className="detail-definition-grid wide">
    <Definition label="Cégkód" value={asset.company_code} />
    <Definition label="Belső azonosító" value={visibleInternalId(asset)} />
    <Definition label="Gyári szám" value={asset.serial_number} />
    <Definition label="Gyártó" value={asset.manufacturer} />
    <Definition label="Modell" value={asset.model} />
    <Definition label="Típus" value={asset.type} />
    <Definition label="Kategória" value={asset.category} />
    <Definition label="Állapot" value={asset.status} />
    <Definition label="Ügyfél" value={asset.customer_name} />
    <Definition label="Helyszín" value={asset.location_name} />
    <Definition label="Belső használat" value={asset.internal_use ? 'Igen' : 'Nem'} />
    <Definition label="Vásárlás dátuma" value={formatDate(asset.purchase_date)} />
    <Definition label="Garancia lejárata" value={formatDate(asset.warranty_expiry)} />
    <Definition label="Utolsó karbantartás" value={formatDate(asset.last_maintenance_date)} />
    <Definition label="Szerződéses karbantartási ciklus" value={asset.maintenance_cycle_label} />
    <Definition label="Karbantartási ciklus megjegyzése" value={asset.maintenance_cycle_note} />
    <Definition label="Következő karbantartás" value={formatDate(asset.effective_next_maintenance_date || asset.next_maintenance_date)} />
    <Definition label="Következő dátum forrása" value={asset.maintenance_due_source === 'contract_cycle' ? 'Utolsó karbantartás + szerződéses ciklus' : asset.maintenance_due_source === 'manual' ? 'Kézzel megadott dátum' : null} />
    <Definition label="Létrehozva" value={formatDateTime(asset.created_at)} />
    <Definition label="Módosítva" value={formatDateTime(asset.updated_at)} />
  </div><div className="text-block"><h3>Megjegyzés</h3><p>{asset.note || '—'}</p></div></section>
}

function Definition({ label, value }) { return <div className="definition-item"><span>{label}</span><strong>{value || '—'}</strong></div> }
function OverviewMetric({ label, value, warning = false }) { return <div className={`overview-metric ${warning ? 'warning' : ''}`}><span>{label}</span><strong>{value}</strong></div> }
function ForecastBadge({ component }) { return <span className={`forecast-badge ${component.forecast_status}`}>{component.is_active ? component.forecast_status_label : 'Inaktív'}</span> }
function daysUntil(value) { if (!value) return Infinity; const today = new Date(); today.setHours(0,0,0,0); const date = new Date(`${String(value).slice(0,10)}T00:00:00`); return Math.ceil((date - today) / 86400000) }
function formatDateTime(value) { if (!value) return '—'; return new Date(value).toLocaleString('hu-HU') }
function formatDate(value) { if (!value) return '—'; return new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString('hu-HU') }
function formatInteger(value) { if (value === null || value === undefined || value === '') return '—'; return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(value)) }
function formatNumber(value) { if (value === null || value === undefined || value === '') return '—'; return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 1 }).format(Number(value)) }
