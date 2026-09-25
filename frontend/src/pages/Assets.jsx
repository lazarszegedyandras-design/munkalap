import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, exportUrl } from '../api.js'
import AssetQuickMeterModal from '../components/AssetQuickMeterModal.jsx'
import { assetLabel, visibleInternalId } from '../utils/assets.js'

const statuses = ['aktív', 'hibás', 'javítás alatt', 'selejtezett', 'raktáron']
const emptyOptions = { company_codes: [], manufacturers: [], types: [], categories: [] }
const emptySummary = { total: 0, active: 0, problem: 0, maintenance: 0, maintenance_missing: 0, component_due: 0, stale_meters: 0 }
const emptyPage = { items: [], page: 1, page_size: 50, total: 0, pages: 1, sort: 'company_code', order: 'asc', summary: emptySummary }
const advancedFilterNames = ['status', 'status_group', 'company_code', 'customer_id', 'location_id', 'manufacturer', 'type', 'category', 'maintenance_state', 'meter_state', 'forecast_state']

export default function Assets({ user }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [pageData, setPageData] = useState(emptyPage)
  const [customers, setCustomers] = useState([])
  const [locations, setLocations] = useState([])
  const [filterOptions, setFilterOptions] = useState(emptyOptions)
  const [filtersOpen, setFiltersOpen] = useState(() => advancedFilterNames.some((name) => searchParams.get(name)))
  const [quickMeterAsset, setQuickMeterAsset] = useState(null)
  const [openMenuId, setOpenMenuId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [searchInput, setSearchInput] = useState(searchParams.get('q') || '')
  const menuRootRef = useRef(null)

  const filters = {
    q: searchParams.get('q') || '',
    status: searchParams.get('status') || '',
    status_group: searchParams.get('status_group') || '',
    company_code: searchParams.get('company_code') || '',
    customer_id: searchParams.get('customer_id') || '',
    location_id: searchParams.get('location_id') || '',
    manufacturer: searchParams.get('manufacturer') || '',
    type: searchParams.get('type') || '',
    category: searchParams.get('category') || '',
    maintenance_state: searchParams.get('maintenance_state') || '',
    meter_state: searchParams.get('meter_state') || '',
    forecast_state: searchParams.get('forecast_state') || '',
  }
  const page = positiveInteger(searchParams.get('page'), 1)
  const pageSize = allowedPageSize(searchParams.get('page_size'))
  const sort = searchParams.get('sort') || 'company_code'
  const order = searchParams.get('order') === 'desc' ? 'desc' : 'asc'
  const assets = pageData.items || []
  const summary = pageData.summary || emptySummary
  const canEdit = ['Admin', 'Irodai felhasználó'].includes(user?.role?.name)
  const canDelete = user?.role?.name === 'Admin'

  useEffect(() => {
    let active = true
    async function loadBase() {
      try {
        const [customerRows, locationRows, options] = await Promise.all([
          api('/customers'),
          api('/locations'),
          api('/assets/filter-options'),
        ])
        if (!active) return
        setCustomers(customerRows)
        setLocations(locationRows)
        setFilterOptions(options || emptyOptions)
      } catch (err) {
        if (active) setError(err.message)
      }
    }
    loadBase()
    return () => { active = false }
  }, [])

  useEffect(() => {
    setSearchInput(filters.q)
  }, [filters.q])

  useEffect(() => {
    if (searchInput === filters.q) return undefined
    const timeout = window.setTimeout(() => {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous)
        const normalized = searchInput.trim()
        if (normalized) next.set('q', normalized)
        else next.delete('q')
        next.delete('page')
        next.delete('printer_asset_id')
        return next
      }, { replace: true })
    }, 350)
    return () => window.clearTimeout(timeout)
  }, [searchInput, filters.q, setSearchParams])

  useEffect(() => {
    let active = true
    async function loadAssets() {
      setLoading(true)
      setError('')
      try {
        const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value))
        params.set('page', String(page))
        params.set('page_size', String(pageSize))
        params.set('sort', sort)
        params.set('order', order)
        const data = await api(`/assets/paged?${params}`)
        if (!active) return
        setPageData(data)
        if (data.page !== page) {
          setSearchParams((previous) => {
            const next = new URLSearchParams(previous)
            if (data.page > 1) next.set('page', String(data.page))
            else next.delete('page')
            return next
          }, { replace: true })
        }
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    loadAssets()
    return () => { active = false }
  }, [
    filters.q,
    filters.status,
    filters.status_group,
    filters.company_code,
    filters.customer_id,
    filters.location_id,
    filters.manufacturer,
    filters.type,
    filters.category,
    filters.maintenance_state,
    filters.meter_state,
    filters.forecast_state,
    page,
    pageSize,
    sort,
    order,
    reloadKey,
    setSearchParams,
  ])

  useEffect(() => {
    const legacyId = searchParams.get('printer_asset_id')
    if (legacyId) navigate(`/assets/${legacyId}?tab=tracking`, { replace: true })
  }, [navigate, searchParams])

  useEffect(() => {
    if (advancedFilterNames.some((name) => filters[name])) setFiltersOpen(true)
  }, [filters.status, filters.status_group, filters.company_code, filters.customer_id, filters.location_id, filters.manufacturer, filters.type, filters.category, filters.maintenance_state, filters.meter_state, filters.forecast_state])

  useEffect(() => {
    function closeMenu(event) {
      if (!menuRootRef.current?.contains(event.target)) setOpenMenuId(null)
    }
    document.addEventListener('mousedown', closeMenu)
    return () => document.removeEventListener('mousedown', closeMenu)
  }, [])

  const locationOptions = useMemo(
    () => locations.filter((location) => !filters.customer_id || location.customer_id === Number(filters.customer_id)),
    [locations, filters.customer_id],
  )

  function updateFilter(name, value) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(name, value)
      else next.delete(name)
      if (name === 'customer_id') next.delete('location_id')
      if (name === 'status') next.delete('status_group')
      if (name === 'status_group') next.delete('status')
      if (!['page', 'page_size'].includes(name)) next.delete('page')
      if (name === 'page_size') next.delete('page')
      next.delete('printer_asset_id')
      return next
    }, { replace: true })
  }

  function applyFilterSet(values) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      Object.entries(values).forEach(([name, value]) => {
        if (value) next.set(name, value)
        else next.delete(name)
      })
      next.delete('page')
      next.delete('printer_asset_id')
      return next
    }, { replace: true })
  }

  function resetFilters() {
    setSearchInput('')
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  function changeSort(field) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      const currentSort = next.get('sort') || 'company_code'
      const currentOrder = next.get('order') === 'desc' ? 'desc' : 'asc'
      next.set('sort', field)
      if (currentSort === field) next.set('order', currentOrder === 'asc' ? 'desc' : 'asc')
      else next.set('order', 'asc')
      next.delete('page')
      return next
    }, { replace: true })
  }

  async function remove(asset) {
    setOpenMenuId(null)
    if (!confirm(`Biztosan törlöd ezt az eszközt?\n\n${assetLabel(asset)}`)) return
    try {
      await api(`/assets/${asset.id}`, { method: 'DELETE' })
      setReloadKey((value) => value + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  async function downloadCsv() {
    try {
      const response = await fetch(exportUrl('/export/assets.csv'), { credentials: 'include' })
      if (!response.ok) throw new Error('A CSV export nem sikerült')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'eszkozok.csv'
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }

  const activeFilterCount = Object.values(filters).filter(Boolean).length
  const searchPending = searchInput.trim() !== filters.q

  return (
    <section className="assets-list-page">
      <div className="page-head assets-page-head">
        <div>
          <h1>Eszközök</h1>
          <p className="muted">Szerveroldali lapozás, rendezés és szűrés nagyobb eszközállományhoz.</p>
        </div>
        <div className="form-actions">
          <button className="secondary" onClick={downloadCsv}>CSV export</button>
          {canEdit && <Link className="button" to="/assets/new">+ Új eszköz</Link>}
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="asset-summary-grid round-two">
        <SummaryCard label="Találatok" value={summary.total} active={activeFilterCount === 0} onClick={resetFilters} />
        <SummaryCard label="Aktív" value={summary.active} tone="tone-success" active={filters.status === 'aktív'} onClick={() => updateFilter('status', filters.status === 'aktív' ? '' : 'aktív')} />
        <SummaryCard label="Hibás / javítás alatt" value={summary.problem} tone={summary.problem ? 'tone-danger' : ''} active={filters.status_group === 'problem'} onClick={() => applyFilterSet({ status: '', status_group: filters.status_group === 'problem' ? '' : 'problem' })} />
        <SummaryCard label="Karbantartás 30 napon belül" value={summary.maintenance} tone={summary.maintenance ? 'tone-warning' : ''} active={filters.maintenance_state === 'due'} onClick={() => updateFilter('maintenance_state', filters.maintenance_state === 'due' ? '' : 'due')} />
        <SummaryCard label="Hiányzó karbantartási adat" value={summary.maintenance_missing} tone={summary.maintenance_missing ? 'tone-muted' : ''} active={filters.maintenance_state === 'missing_last'} onClick={() => updateFilter('maintenance_state', filters.maintenance_state === 'missing_last' ? '' : 'missing_last')} />
        <SummaryCard label="Alkatrészcsere 30 napon belül" value={summary.component_due} tone={summary.component_due ? 'tone-warning' : ''} active={filters.forecast_state === 'due'} onClick={() => updateFilter('forecast_state', filters.forecast_state === 'due' ? '' : 'due')} />
        <SummaryCard label="Hiányos / régi számláló" value={summary.stale_meters} tone={summary.stale_meters ? 'tone-muted' : ''} active={filters.meter_state === 'needs_update'} onClick={() => updateFilter('meter_state', filters.meter_state === 'needs_update' ? '' : 'needs_update')} />
      </div>

      <div className="panel asset-filter-panel">
        <div className="asset-search-row">
          <div className="debounced-search-wrap">
            <input
              aria-label="Eszköz keresése"
              placeholder="Keresés cégkód, gyári szám, típus, modell, gyártó, ügyfél vagy helyszín szerint..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            {searchPending && <span className="search-pending">Keresés...</span>}
          </div>
          <button type="button" className="secondary" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((value) => !value)}>
            Részletes szűrők{activeFilterCount ? ` (${activeFilterCount})` : ''}
          </button>
          {activeFilterCount > 0 && <button type="button" className="ghost-button" onClick={resetFilters}>Alaphelyzet</button>}
        </div>
        {filtersOpen && <div className="asset-advanced-filters round-two">
          <FilterField label="Állapot"><select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)}><option value="">Összes állapot</option>{statuses.map((status) => <option key={status}>{status}</option>)}</select></FilterField>
          <FilterField label="Cégkód"><select value={filters.company_code} onChange={(event) => updateFilter('company_code', event.target.value)}><option value="">Összes cég</option>{filterOptions.company_codes.map((value) => <option key={value}>{value}</option>)}</select></FilterField>
          <FilterField label="Ügyfél"><select value={filters.customer_id} onChange={(event) => updateFilter('customer_id', event.target.value)}><option value="">Összes ügyfél</option>{customers.map((customer) => <option value={customer.id} key={customer.id}>{customer.company_code ? `${customer.company_code} · ` : ''}{customer.name}</option>)}</select></FilterField>
          <FilterField label="Helyszín"><select value={filters.location_id} onChange={(event) => updateFilter('location_id', event.target.value)} disabled={!filters.customer_id}><option value="">Összes helyszín</option>{locationOptions.map((location) => <option value={location.id} key={location.id}>{location.name}{location.is_active === false ? ' · inaktív' : ''}</option>)}</select></FilterField>
          <FilterField label="Gyártó"><select value={filters.manufacturer} onChange={(event) => updateFilter('manufacturer', event.target.value)}><option value="">Összes gyártó</option>{filterOptions.manufacturers.map((value) => <option key={value}>{value}</option>)}</select></FilterField>
          <FilterField label="Típus"><select value={filters.type} onChange={(event) => updateFilter('type', event.target.value)}><option value="">Összes típus</option>{filterOptions.types.map((value) => <option key={value}>{value}</option>)}</select></FilterField>
          <FilterField label="Kategória"><select value={filters.category} onChange={(event) => updateFilter('category', event.target.value)}><option value="">Összes kategória</option>{filterOptions.categories.map((value) => <option key={value}>{value}</option>)}</select></FilterField>
          <FilterField label="Karbantartás"><select value={filters.maintenance_state} onChange={(event) => updateFilter('maintenance_state', event.target.value)}><option value="">Bármely karbantartási állapot</option><option value="due">Lejárt vagy 30 napon belüli</option><option value="overdue">Lejárt</option><option value="due_30_days">30 napon belül</option><option value="future">Később esedékes</option><option value="missing_last">Nincs utolsó karbantartási adat</option><option value="none">Nincs ütemezve</option></select></FilterField>
          <FilterField label="Számlálóadat"><select value={filters.meter_state} onChange={(event) => updateFilter('meter_state', event.target.value)}><option value="">Bármely számlálóállapot</option><option value="fresh">Aktuális</option><option value="needs_update">Hiányos vagy 30 napnál régebbi</option><option value="stale">30 napnál régebbi</option><option value="missing">Nincs adat</option></select></FilterField>
          <FilterField label="Alkatrész-előrejelzés"><select value={filters.forecast_state} onChange={(event) => updateFilter('forecast_state', event.target.value)}><option value="">Bármely előrejelzés</option><option value="due">Esedékes vagy 30 napon belüli</option><option value="overdue">Csere esedékes</option><option value="due_30_days">30 napon belül</option><option value="forecast_available">Későbbi előrejelzés</option><option value="insufficient_data">Nincs elegendő adat</option><option value="none">Nincs követett alkatrész</option></select></FilterField>
        </div>}
        {activeFilterCount > 0 && <div className="filter-chips">
          {filters.q && <FilterChip label={`Keresés: ${filters.q}`} onRemove={() => { setSearchInput(''); updateFilter('q', '') }} />}
          {filters.status && <FilterChip label={`Állapot: ${filters.status}`} onRemove={() => updateFilter('status', '')} />}
          {filters.status_group && <FilterChip label="Állapot: hibás / javítás alatt" onRemove={() => updateFilter('status_group', '')} />}
          {filters.company_code && <FilterChip label={`Cég: ${filters.company_code}`} onRemove={() => updateFilter('company_code', '')} />}
          {filters.customer_id && <FilterChip label={`Ügyfél: ${customers.find((customer) => customer.id === Number(filters.customer_id))?.name || filters.customer_id}`} onRemove={() => updateFilter('customer_id', '')} />}
          {filters.location_id && <FilterChip label={`Helyszín: ${locations.find((location) => location.id === Number(filters.location_id))?.name || filters.location_id}`} onRemove={() => updateFilter('location_id', '')} />}
          {filters.manufacturer && <FilterChip label={`Gyártó: ${filters.manufacturer}`} onRemove={() => updateFilter('manufacturer', '')} />}
          {filters.type && <FilterChip label={`Típus: ${filters.type}`} onRemove={() => updateFilter('type', '')} />}
          {filters.category && <FilterChip label={`Kategória: ${filters.category}`} onRemove={() => updateFilter('category', '')} />}
          {filters.maintenance_state && <FilterChip label={`Karbantartás: ${maintenanceLabel(filters.maintenance_state)}`} onRemove={() => updateFilter('maintenance_state', '')} />}
          {filters.meter_state && <FilterChip label={`Számláló: ${meterLabel(filters.meter_state)}`} onRemove={() => updateFilter('meter_state', '')} />}
          {filters.forecast_state && <FilterChip label={`Alkatrész: ${forecastLabel(filters.forecast_state)}`} onRemove={() => updateFilter('forecast_state', '')} />}
        </div>}
      </div>

      <div className="asset-list-toolbar">
        <span>{pageData.total} találat · {pageData.page}. / {pageData.pages}. oldal</span>
        <label>Oldalméret
          <select value={pageSize} onChange={(event) => updateFilter('page_size', event.target.value)}>
            {[25, 50, 100, 200].map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>

      <div className="table-wrap asset-table-wrap" ref={menuRootRef} aria-busy={loading}>
        <table className="asset-list-table round-two">
          <thead><tr>
            <SortableHeader label="Állapot" field="status" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Cégkód" field="company_code" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Eszköz" field="display_name" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Ügyfél / helyszín" field="customer_name" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Gyári szám" field="serial_number" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Utolsó karbantartás" field="last_maintenance_date" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Szerződéses ciklus" field="maintenance_cycle_months" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Számláló" field="latest_meter_value" sort={sort} order={order} onSort={changeSort} />
            <SortableHeader label="Következő esemény" field="next_event" sort={sort} order={order} onSort={changeSort} />
            <th aria-label="Műveletek"></th>
          </tr></thead>
          <tbody>
            {loading && <tr><td colSpan="10"><div className="table-loading">Eszközök betöltése...</div></td></tr>}
            {!loading && assets.length === 0 && <tr><td colSpan="10"><div className="empty-state"><strong>Nincs a szűrésnek megfelelő eszköz.</strong><button type="button" className="secondary" onClick={resetFilters}>Szűrők törlése</button></div></td></tr>}
            {!loading && assets.map((asset) => <tr key={asset.id} className="clickable-row" tabIndex="0" onClick={() => navigate(`/assets/${asset.id}`)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') navigate(`/assets/${asset.id}`) }}>
              <td><StatusBadge status={asset.status} /></td>
              <td><span className="company-code-badge">{asset.company_code || '—'}</span></td>
              <td><div className="asset-primary-cell"><strong>{asset.display_name || assetLabel(asset)}</strong><small>{[asset.manufacturer, asset.model, asset.type].filter(Boolean).join(' · ') || visibleInternalId(asset) || 'Nincs további törzsadat'}</small></div></td>
              <td><strong>{asset.customer_name || (asset.internal_use ? 'Belső használat' : 'Nincs ügyfél')}</strong><small className="cell-subline">{asset.location_name || 'Nincs helyszín'}</small></td>
              <td>{asset.serial_number || '—'}</td>
              <td><MaintenanceCell asset={asset} /></td>
              <td><CycleCell asset={asset} /></td>
              <td><MeterCell asset={asset} /></td>
              <td><NextEvent asset={asset} /></td>
              <td className="asset-menu-cell" onClick={(event) => event.stopPropagation()}>
                <button type="button" className="icon-button menu-trigger" aria-label="Eszközműveletek" aria-expanded={openMenuId === asset.id} onClick={() => setOpenMenuId((current) => current === asset.id ? null : asset.id)}>⋮</button>
                {openMenuId === asset.id && <div className="row-action-menu">
                  <button type="button" onClick={() => navigate(`/assets/${asset.id}`)}>Megnyitás</button>
                  {canEdit && <button type="button" onClick={() => navigate(`/assets/${asset.id}/edit`)}>Szerkesztés</button>}
                  <button type="button" onClick={() => { setOpenMenuId(null); setQuickMeterAsset(asset) }}>Számláló rögzítése</button>
                  <button type="button" onClick={() => navigate(`/work-orders/new?new_asset_id=${asset.id}`)}>Új munkalap</button>
                  {canDelete && <><div className="menu-separator" /><button type="button" className="danger-text" onClick={() => remove(asset)}>Törlés</button></>}
                </div>}
              </td>
            </tr>)}
          </tbody>
        </table>
      </div>

      <Pagination current={pageData.page} pages={pageData.pages} onChange={(value) => updateFilter('page', value > 1 ? String(value) : '')} />

      {quickMeterAsset && <AssetQuickMeterModal asset={quickMeterAsset} onClose={() => setQuickMeterAsset(null)} onSaved={() => setReloadKey((value) => value + 1)} />}
    </section>
  )
}

function SummaryCard({ label, value, tone = '', active = false, onClick }) {
  return <button type="button" className={`asset-summary-card ${tone} ${active ? 'active' : ''}`} onClick={onClick}><span>{label}</span><strong>{value}</strong></button>
}

function FilterField({ label, children }) {
  return <label className="asset-filter-field"><span>{label}</span>{children}</label>
}

function FilterChip({ label, onRemove }) {
  return <span className="filter-chip">{label}<button type="button" aria-label={`${label} törlése`} onClick={onRemove}>×</button></span>
}

function SortableHeader({ label, field, sort, order, onSort }) {
  const active = sort === field
  const direction = active ? order : null
  return <th aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}>
    <button type="button" className={`sortable-header ${active ? 'active' : ''}`} onClick={() => onSort(field)}>
      <span>{label}</span><span aria-hidden="true">{direction === 'asc' ? '▲' : direction === 'desc' ? '▼' : '↕'}</span>
    </button>
  </th>
}

function Pagination({ current, pages, onChange }) {
  if (pages <= 1) return null
  const entries = paginationEntries(current, pages)
  return <nav className="asset-pagination" aria-label="Eszközlista lapozása">
    <button type="button" className="secondary" disabled={current <= 1} onClick={() => onChange(current - 1)}>Előző</button>
    <div className="pagination-pages">
      {entries.map((entry, index) => entry === '…'
        ? <span key={`ellipsis-${index}`} className="pagination-ellipsis">…</span>
        : <button type="button" key={entry} className={entry === current ? 'active' : ''} aria-current={entry === current ? 'page' : undefined} onClick={() => onChange(entry)}>{entry}</button>)}
    </div>
    <button type="button" className="secondary" disabled={current >= pages} onClick={() => onChange(current + 1)}>Következő</button>
  </nav>
}

export function StatusBadge({ status }) {
  const css = String(status || '').replaceAll(' ', '-').replaceAll('/', '-')
  return <span className={`asset-status-badge status-${css}`}>{status || 'nincs állapot'}</span>
}

function MaintenanceCell({ asset }) {
  if (!asset.last_maintenance_date) {
    return <div className="maintenance-date-cell"><strong>—</strong><span className="signal-badge neutral">Nincs adat</span></div>
  }
  const days = asset.maintenance_days_since_last
  return <div className="maintenance-date-cell"><strong>{formatDate(asset.last_maintenance_date)}</strong><small>{days === 0 ? 'ma' : days != null ? `${days} napja` : ''}</small></div>
}

function CycleCell({ asset }) {
  const label = asset.maintenance_cycle_label || (asset.maintenance_cycle_months ? `${asset.maintenance_cycle_months} hónap` : null)
  if (!label) return <span className="muted">Nincs megadva</span>
  return <div className="cycle-cell"><strong>{label}</strong>{asset.maintenance_cycle_note && asset.maintenance_cycle_months ? <small>{asset.maintenance_cycle_note}</small> : null}</div>
}

function MeterCell({ asset }) {
  if (asset.latest_meter_value === null || asset.latest_meter_value === undefined) {
    return <div className="meter-cell"><strong>—</strong><span className="signal-badge neutral">Nincs adat</span></div>
  }
  const age = asset.meter_age_days === 0 ? 'ma rögzítve' : `${asset.meter_age_days} napos adat`
  const stale = asset.meter_state === 'stale'
  return <div className="meter-cell"><strong>{formatInteger(asset.latest_meter_value)}</strong><small>{age}</small>{stale && <span className="signal-badge warning">Frissítendő</span>}</div>
}

function NextEvent({ asset }) {
  const candidates = []
  const maintenanceDate = asset.effective_next_maintenance_date || asset.next_maintenance_date
  if (maintenanceDate) {
    candidates.push({
      kind: 'Karbantartás',
      date: new Date(`${maintenanceDate}T00:00:00`),
      status: asset.maintenance_state,
      label: asset.maintenance_state_label,
    })
  }
  if (asset.next_component_name) {
    candidates.push({
      kind: asset.next_component_name,
      date: asset.next_component_forecast_at ? new Date(asset.next_component_forecast_at) : null,
      status: asset.component_forecast_status,
      label: asset.component_forecast_status_label,
    })
  }
  if (!candidates.length) return <span className="muted">Nincs ütemezett esemény</span>
  candidates.sort((a, b) => eventPriority(a) - eventPriority(b) || ((a.date?.getTime() || Infinity) - (b.date?.getTime() || Infinity)))
  const primary = candidates[0]
  const dateText = primary.date ? primary.date.toLocaleDateString('hu-HU') : primary.label
  return <div className={`next-event ${eventTone(primary.status)}`}><strong>{primary.kind}</strong><small>{dateText}{primary.date ? ` · ${relativeDate(primary.date)}` : ''}</small><span className={`signal-badge ${eventTone(primary.status)}`}>{primary.label}</span></div>
}

function paginationEntries(current, pages) {
  const values = new Set([1, pages, current - 2, current - 1, current, current + 1, current + 2])
  const sorted = [...values].filter((value) => value >= 1 && value <= pages).sort((a, b) => a - b)
  const result = []
  sorted.forEach((value, index) => {
    if (index > 0 && value - sorted[index - 1] > 1) result.push('…')
    result.push(value)
  })
  return result
}

function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(value || '', 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function allowedPageSize(value) {
  const parsed = positiveInteger(value, 50)
  return [25, 50, 100, 200].includes(parsed) ? parsed : 50
}

function eventPriority(item) {
  if (item.status === 'overdue') return 0
  if (item.status === 'due_30_days') return 1
  if (item.status === 'insufficient_data') return 4
  if (item.status === 'none') return 5
  return 2
}
function eventTone(status) {
  if (status === 'overdue') return 'overdue'
  if (status === 'due_30_days') return 'soon'
  if (status === 'insufficient_data' || status === 'none') return 'neutral'
  return 'normal'
}
function relativeDate(date) {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const target = new Date(date); target.setHours(0, 0, 0, 0)
  const days = Math.ceil((target - today) / 86400000)
  if (days < 0) return `${Math.abs(days)} napja lejárt`
  if (days === 0) return 'ma esedékes'
  return `${days} nap múlva`
}
function maintenanceLabel(value) { return ({ due: 'lejárt / 30 napon belül', needs_planning: 'munkaszervezést igényel', overdue: 'lejárt', due_30_days: '30 napon belül', future: 'később esedékes', missing_last: 'nincs utolsó karbantartási adat', none: 'nincs ütemezve' })[value] || value }
function meterLabel(value) { return ({ fresh: 'aktuális', needs_update: 'hiányos / 30 napnál régebbi', stale: '30 napnál régebbi', missing: 'nincs adat' })[value] || value }
function forecastLabel(value) { return ({ due: 'esedékes / 30 napon belül', overdue: 'csere esedékes', due_30_days: '30 napon belül', forecast_available: 'későbbi előrejelzés', insufficient_data: 'nincs elegendő adat', none: 'nincs követett alkatrész' })[value] || value }
function formatInteger(value) { return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(value)) }
function formatDate(value) { if (!value) return '—'; return new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString('hu-HU') }
