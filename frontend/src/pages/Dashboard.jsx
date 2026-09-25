import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

const HOUR_HEIGHT = 64
const DAY_NAMES = ['Hétfő', 'Kedd', 'Szerda', 'Csütörtök', 'Péntek', 'Szombat', 'Vasárnap']
const TECHNICIAN_COLORS = [
  { border: '#2563eb', background: '#dbeafe', text: '#1e3a8a' },
  { border: '#059669', background: '#d1fae5', text: '#064e3b' },
  { border: '#d97706', background: '#fef3c7', text: '#78350f' },
  { border: '#7c3aed', background: '#ede9fe', text: '#4c1d95' },
  { border: '#db2777', background: '#fce7f3', text: '#831843' },
  { border: '#0891b2', background: '#cffafe', text: '#164e63' },
  { border: '#dc2626', background: '#fee2e2', text: '#7f1d1d' },
  { border: '#4f46e5', background: '#e0e7ff', text: '#312e81' },
]
const UNASSIGNED_COLOR = { border: '#64748b', background: '#e2e8f0', text: '#334155' }

function startOfWeek(value = new Date()) {
  const date = new Date(value)
  date.setHours(0, 0, 0, 0)
  const day = date.getDay()
  const distance = day === 0 ? -6 : 1 - day
  date.setDate(date.getDate() + distance)
  return date
}

function addDays(value, days) {
  const result = new Date(value)
  result.setDate(result.getDate() + days)
  return result
}

function toDateKey(value) {
  const date = new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDay(value) {
  return new Intl.DateTimeFormat('hu-HU', { month: 'short', day: 'numeric' }).format(new Date(value))
}

function formatTime(value) {
  return new Intl.DateTimeFormat('hu-HU', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function formatWeekRange(start) {
  const end = addDays(start, 6)
  const formatter = new Intl.DateTimeFormat('hu-HU', { year: 'numeric', month: 'long', day: 'numeric' })
  return `${formatter.format(start)} – ${formatter.format(end)}`
}

function durationSourceLabel(source) {
  return {
    actual: 'Tényleges idő',
    mixed: 'Tervezett kezdés / tényleges befejezés',
    labor_derived: 'Rögzített munkaidőből számított időtartam',
    planned: 'Tervezett idő',
    in_progress: 'Folyamatban',
    date_fallback: 'Időpont nélkül, alapértelmezett blokk',
  }[source] || source
}

function leaveTypeLabel(type) {
  return type === 'sick_leave' ? 'Betegszabadság' : 'Szabadság'
}

function leaveOccursOnDay(event, day) {
  const dayKey = toDateKey(day)
  return event.start_date <= dayKey && event.end_date >= dayKey
}

function layoutDayEvents(events, day) {
  const dayStart = new Date(day)
  dayStart.setHours(0, 0, 0, 0)
  const dayEnd = addDays(dayStart, 1)
  const items = events
    .map((event) => {
      const originalStart = new Date(event.start)
      const originalEnd = new Date(event.end)
      if (originalStart >= dayEnd || originalEnd <= dayStart) return null
      return {
        ...event,
        clippedStart: originalStart < dayStart ? dayStart : originalStart,
        clippedEnd: originalEnd > dayEnd ? dayEnd : originalEnd,
      }
    })
    .filter(Boolean)
    .sort((a, b) => a.clippedStart - b.clippedStart || a.clippedEnd - b.clippedEnd)

  const result = []
  let cluster = []
  let clusterEnd = null

  function flushCluster() {
    if (!cluster.length) return
    const laneEnds = []
    const laidOut = cluster.map((event) => {
      let lane = laneEnds.findIndex((end) => end <= event.clippedStart)
      if (lane === -1) lane = laneEnds.length
      laneEnds[lane] = event.clippedEnd
      return { ...event, lane }
    })
    const laneCount = Math.max(1, laneEnds.length)
    laidOut.forEach((event) => result.push({ ...event, laneCount }))
    cluster = []
    clusterEnd = null
  }

  items.forEach((event) => {
    if (clusterEnd && event.clippedStart >= clusterEnd) flushCluster()
    cluster.push(event)
    clusterEnd = !clusterEnd || event.clippedEnd > clusterEnd ? event.clippedEnd : clusterEnd
  })
  flushCluster()
  return result
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [summary, setSummary] = useState(null)
  const [calendar, setCalendar] = useState(null)
  const [printerMaintenance, setPrinterMaintenance] = useState(null)
  const [maintenancePlanning, setMaintenancePlanning] = useState(null)
  const [weekStart, setWeekStart] = useState(() => startOfWeek())
  const [error, setError] = useState('')
  const [loadingCalendar, setLoadingCalendar] = useState(false)

  useEffect(() => {
    Promise.all([api('/dashboard/summary'), api('/dashboard/printer-maintenance'), api('/dashboard/maintenance-planning')])
      .then(([summaryData, printerData, maintenanceData]) => { setSummary(summaryData); setPrinterMaintenance(printerData); setMaintenancePlanning(maintenanceData) })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    setLoadingCalendar(true)
    setError('')
    api(`/dashboard/calendar?week_start=${toDateKey(weekStart)}`)
      .then(setCalendar)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingCalendar(false))
  }, [weekStart])

  const cards = [
    ['Nyitott munkalapok', summary?.open_work_orders],
    ['Sürgős munkalapok', summary?.urgent_work_orders],
    ['Ma esedékes', summary?.due_today_work_orders],
    ['Lejárt karbantartások', summary?.due_maintenance_assets],
    ['30 napon belüli karbantartások', summary?.due_soon_maintenance_assets],
    ['Hiányzó karbantartási adat', summary?.missing_maintenance_assets],
    ['Hibás / javítás alatt', summary?.faulty_assets],
    ['Esedékes alkatrészcserék', printerMaintenance?.overdue_count],
    ['30 napon belüli cserék', printerMaintenance?.due_30_days_count],
    ['Elavult számlálóadat', printerMaintenance?.stale_meter_assets_count],
  ]

  const events = calendar?.events || []
  const leaveEvents = calendar?.leave_events || []
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart])
  const technicianIds = useMemo(() => {
    const ids = [...(calendar?.technicians || []).map((item) => item.id)]
    events.forEach((event) => {
      if (event.technician_id && !ids.includes(event.technician_id)) ids.push(event.technician_id)
    })
    leaveEvents.forEach((event) => {
      if (event.technician_id && !ids.includes(event.technician_id)) ids.push(event.technician_id)
    })
    return ids
  }, [calendar, events, leaveEvents])

  function technicianColor(technicianId) {
    if (!technicianId) return UNASSIGNED_COLOR
    const index = Math.max(0, technicianIds.indexOf(technicianId))
    return TECHNICIAN_COLORS[index % TECHNICIAN_COLORS.length]
  }

  const { startHour, endHour } = useMemo(() => {
    if (!events.length) return { startHour: 7, endHour: 19 }
    const intervals = events.map((event) => ({ start: new Date(event.start), end: new Date(event.end) }))
    const spansMultipleDays = intervals.some(({ start, end }) => toDateKey(start) !== toDateKey(end))
    if (spansMultipleDays) return { startHour: 0, endHour: 24 }
    const earliest = Math.min(...intervals.map(({ start }) => start.getHours()))
    const latest = Math.max(...intervals.map(({ end }) => end.getHours() + (end.getMinutes() > 0 ? 1 : 0)))
    return { startHour: Math.max(0, Math.min(7, earliest)), endHour: Math.min(24, Math.max(19, latest)) }
  }, [events])

  const hourCount = endHour - startHour
  const calendarHeight = hourCount * HOUR_HEIGHT
  const hours = Array.from({ length: hourCount + 1 }, (_, index) => startHour + index)
  const todayKey = toDateKey(new Date())
  const now = new Date()

  return (
    <section>
      <div className="page-head"><h1>Dashboard</h1></div>
      {error && <div className="error">{error}</div>}
      <div className="cards">
        {cards.map(([label, value]) => (
          <div className="metric" key={label}><span>{label}</span><strong>{value ?? '-'}</strong></div>
        ))}
      </div>

      <div className="panel calendar-panel">
        <div className="calendar-toolbar">
          <div>
            <h2>Heti munkalap-naptár</h2>
            <p className="muted">{formatWeekRange(weekStart)}</p>
          </div>
          <div className="form-actions">
            <button type="button" className="secondary" onClick={() => setWeekStart(addDays(weekStart, -7))}>Előző hét</button>
            <button type="button" className="secondary" onClick={() => setWeekStart(startOfWeek())}>Aktuális hét</button>
            <button type="button" className="secondary" onClick={() => setWeekStart(addDays(weekStart, 7))}>Következő hét</button>
          </div>
        </div>

        <div className="calendar-legends">
          <div className="technician-legend">
            {(calendar?.technicians || []).map((technician) => {
              const color = technicianColor(technician.id)
              return <span className="legend-item" key={technician.id}><i style={{ background: color.background, borderColor: color.border }} />{technician.name}</span>
            })}
            {events.some((event) => !event.technician_id) && <span className="legend-item"><i style={{ background: UNASSIGNED_COLOR.background, borderColor: UNASSIGNED_COLOR.border }} />Nincs kijelölve</span>}
          </div>
          <div className="status-legend">
            <span><i className="status-sample open" /> Nyitott / tervezett</span>
            <span><i className="status-sample closed" /> Lezárt / tényleges</span>
            <span><i className="status-sample leave" /> Jóváhagyott távollét</span>
          </div>
        </div>

        {loadingCalendar ? <p>Naptár betöltése...</p> : (
          <div className="calendar-scroll">
            <div className="calendar-week">
              <div className="calendar-header-grid">
                <div className="calendar-corner">Idő</div>
                {days.map((day, index) => (
                  <div className={`calendar-day-head ${toDateKey(day) === todayKey ? 'today' : ''} ${index >= 5 ? 'weekend' : ''}`} key={toDateKey(day)}>
                    <strong>{DAY_NAMES[index]}</strong><span>{formatDay(day)}</span>
                  </div>
                ))}
              </div>

              {leaveEvents.length > 0 && <div className="calendar-leave-grid">
                <div className="calendar-leave-axis">Távollét</div>
                {days.map((day) => (
                  <div className="calendar-leave-day" key={`leave-${toDateKey(day)}`}>
                    {leaveEvents.filter((event) => leaveOccursOnDay(event, day)).map((event) => {
                      const color = technicianColor(event.technician_id)
                      return <div
                        className={`calendar-leave-event ${event.leave_type}`}
                        key={`${event.id}-${toDateKey(day)}`}
                        title={`${event.technician_name} · ${leaveTypeLabel(event.leave_type)} · ${event.start_date}–${event.end_date}`}
                        style={{ '--event-border': color.border, '--event-background': color.background, '--event-text': color.text }}
                      ><strong>{event.technician_name}</strong><span>{leaveTypeLabel(event.leave_type)}</span></div>
                    })}
                  </div>
                ))}
              </div>}

              <div className="calendar-body-grid" style={{ height: `${calendarHeight}px` }}>
                <div className="calendar-time-axis">
                  {hours.map((hour, index) => <span key={hour} style={{ top: `${index * HOUR_HEIGHT - 8}px` }}>{String(hour).padStart(2, '0')}:00</span>)}
                </div>

                {days.map((day, dayIndex) => {
                  const dayEvents = layoutDayEvents(events, day)
                  const isToday = toDateKey(day) === todayKey
                  const nowTop = ((now.getHours() * 60 + now.getMinutes()) - startHour * 60) / 60 * HOUR_HEIGHT
                  return (
                    <div className={`calendar-day-column ${dayIndex >= 5 ? 'weekend' : ''} ${isToday ? 'today' : ''}`} key={toDateKey(day)}>
                      {hours.map((hour, index) => <div className="calendar-hour-line" key={hour} style={{ top: `${index * HOUR_HEIGHT}px` }} />)}
                      {isToday && nowTop >= 0 && nowTop <= calendarHeight && <div className="calendar-now-line" style={{ top: `${nowTop}px` }}><span /></div>}
                      {dayEvents.map((event) => {
                        const color = technicianColor(event.technician_id)
                        const dayStart = new Date(day)
                        dayStart.setHours(0, 0, 0, 0)
                        const startMinutes = (event.clippedStart - dayStart) / 60000
                        const endMinutes = (event.clippedEnd - dayStart) / 60000
                        const top = ((startMinutes - startHour * 60) / 60) * HOUR_HEIGHT
                        const height = Math.max(28, ((endMinutes - startMinutes) / 60) * HOUR_HEIGHT)
                        const gap = 3
                        const widthPercent = 100 / event.laneCount
                        const leftPercent = event.lane * widthPercent
                        const title = `${event.number}\n${event.customer_name}\n${formatTime(event.start)}–${formatTime(event.end)}\n${event.technician_name}\n${durationSourceLabel(event.duration_source)}\n${event.description}`
                        return (
                          <article
                            className={`calendar-event ${event.is_closed ? 'closed' : 'open'} priority-${event.priority}`}
                            key={`${event.id}-${toDateKey(day)}`}
                            title={`${title}
Kattintás: munkalap megnyitása`}
                            role="button"
                            tabIndex={0}
                            aria-label={`${event.number} munkalap megnyitása`}
                            onClick={() => navigate(`/work-orders/${event.id}`)}
                            onKeyDown={(keyboardEvent) => {
                              if (keyboardEvent.key === 'Enter' || keyboardEvent.key === ' ') {
                                keyboardEvent.preventDefault()
                                navigate(`/work-orders/${event.id}`)
                              }
                            }}
                            style={{
                              top: `${top}px`,
                              height: `${height}px`,
                              left: `calc(${leftPercent}% + ${gap}px)`,
                              width: `calc(${widthPercent}% - ${gap * 2}px)`,
                              '--event-border': color.border,
                              '--event-background': color.background,
                              '--event-text': color.text,
                            }}
                          >
                            <div className="calendar-event-title"><strong>{event.is_closed ? '✓ ' : ''}{event.number}</strong><span>{formatTime(event.start)}–{formatTime(event.end)}</span></div>
                            <div className="calendar-event-customer">{event.customer_name}</div>
                            {height >= 52 && <div className="calendar-event-technician">{event.technician_name}</div>}
                          </article>
                        )
                      })}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
        {!loadingCalendar && !events.length && <p className="muted calendar-empty">Ezen a héten nincs időponthoz rendelt munkalap.</p>}
      </div>

      <div className="dashboard-printer-grid">
        <div className="panel">
          <div className="page-head"><h2>Várható alkatrészcserék</h2></div>
          {!printerMaintenance?.due_items?.length && <p className="muted">Nincs esedékes vagy 30 napon belül várható alkatrészcsere.</p>}
          <div className="maintenance-list">
            {(printerMaintenance?.due_items || []).slice(0, 10).map((item) => (
              <button type="button" className={`maintenance-item ${item.status}`} key={`${item.asset_id}-${item.component_id}`} onClick={() => navigate(`/assets/${item.asset_id}?tab=tracking`)}>
                <span><strong>{item.asset_name}</strong><small>{item.customer_name || 'Nincs ügyfél'}{item.location_name ? ` · ${item.location_name}` : ''}</small></span>
                <span><strong>{item.component_name}</strong><small>{item.status_label}{item.forecast_at ? ` · ${formatDateOnly(item.forecast_at)}` : ''}</small></span>
              </button>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="page-head"><h2>Hiányzó / régi számlálóadat</h2></div>
          {!printerMaintenance?.stale_assets?.length && <p className="muted">Minden követett nyomtatónak friss számlálóadata van.</p>}
          <div className="maintenance-list">
            {(printerMaintenance?.stale_assets || []).slice(0, 10).map((item) => (
              <button type="button" className="maintenance-item stale" key={item.asset_id} onClick={() => navigate(`/assets/${item.asset_id}?tab=tracking`)}>
                <span><strong>{item.asset_name}</strong><small>{item.customer_name || 'Nincs ügyfél'}{item.location_name ? ` · ${item.location_name}` : ''}</small></span>
                <span><strong>{item.latest_meter_value !== null ? `${formatInteger(item.latest_meter_value)} oldal` : 'Nincs mérés'}</strong><small>{item.meter_age_days !== null ? `${item.meter_age_days} napos adat` : 'Rögzíts számlálóállást'}</small></span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="panel maintenance-planning-panel">
        <div className="page-head">
          <div><h2>Karbantartási munkaszervezés</h2><p className="muted">Az esedékesség az utolsó karbantartás és a szerződéses ciklus alapján számított.</p></div>
          <div className="maintenance-planning-counts">
            <span className="signal-badge overdue">Lejárt: {maintenancePlanning?.overdue_count ?? '-'}</span>
            <span className="signal-badge soon">30 napon belül: {maintenancePlanning?.due_30_days_count ?? '-'}</span>
            <span className="signal-badge neutral">Hiányzó dátum: {maintenancePlanning?.missing_last_count ?? '-'}</span>
          </div>
        </div>
        {!maintenancePlanning?.items?.length && <p className="muted">Nincs munkaszervezést igénylő karbantartás.</p>}
        <div className="maintenance-list planning-list">
          {(maintenancePlanning?.items || []).slice(0, 20).map((item) => (
            <div className={`maintenance-item ${item.maintenance_state}`} key={item.asset_id}>
              <button type="button" className="maintenance-main-button" onClick={() => navigate(`/assets/${item.asset_id}`)}>
                <span><strong>{item.company_code ? `${item.company_code} · ` : ''}{item.asset_name}</strong><small>{item.customer_name || 'Nincs ügyfél'}{item.location_name ? ` · ${item.location_name}` : ''}</small></span>
                <span><strong>{item.maintenance_state_label}</strong><small>Utolsó: {formatDateOnly(item.last_maintenance_date)} · Ciklus: {item.maintenance_cycle_label || 'nincs megadva'} · Következő: {formatDateOnly(item.effective_next_maintenance_date)}</small></span>
              </button>
              <button type="button" className="secondary small-button" onClick={() => navigate(`/work-orders/new?new_asset_id=${item.asset_id}&maintenance=1`)}>Munkalap</button>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}


function formatDateOnly(value) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('hu-HU', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value))
}

function formatInteger(value) {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(value))
}
