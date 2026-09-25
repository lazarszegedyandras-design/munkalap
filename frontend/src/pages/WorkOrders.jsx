import React, { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, csrfHeaders, exportUrl } from '../api.js'
import DataTable from '../components/DataTable.jsx'
import WorkOrderArchiveTable from '../components/WorkOrderArchiveTable.jsx'
import WorkOrderArchiveUploadModal from '../components/WorkOrderArchiveUploadModal.jsx'
import { Field } from '../components/FormField.jsx'
import { assetLabel, visibleInternalId } from '../utils/assets.js'
import { currentDateTimeLocalValue, toDateTimeLocalValue } from '../utils/datetime.js'
import { assetMachineType, supplierWorksheetEmail, supplierWorksheetPhone, workOrderAssetSummary } from '../utils/workOrders.js'

const statuses = ['új', 'ütemezve', 'folyamatban', 'várakozik', 'kész', 'lezárva', 'törölve / sztornózva']
const priorities = ['alacsony', 'normál', 'sürgős']
const workTypes = ['karbantartás', 'javítás', 'eseti javítás', 'kiszállítás', 'üzembe helyezés']
const emptyMaterialLine = () => ({ material_id: '', quantity: '', unit_price: '', note: '' })
const empty = { version: null, customer_id: '', location_id: '', contact_id: '', contract_id: '', asset_ids: [], description: '', priority: 'normál', status: 'új', technician_id: '', secondary_technician_id: '', planned_date: '', planned_start_at: '', planned_end_at: '', started_at: '', completed_at: '', work_done: '', labor_hours: '', work_type: '', contract_type: '', internal_note: '', materials: [] }
const defaultWorkOrderColumns = ['number', 'status', 'customer', 'location', 'assets', 'description', 'technician', 'planned']
const workOrderColumnOptions = [
  ['number', 'Munkalap'], ['status', 'Státusz'], ['priority', 'Prioritás'], ['customer', 'Ügyfél'], ['location', 'Helyszín'],
  ['assets', 'Gép / gyári szám'], ['description', 'Feladat'], ['technician', 'Technikus'], ['planned', 'Tervezett idő'], ['work_type', 'Munka típusa'],
  ['created_at', 'Létrehozva'], ['updated_at', 'Módosítva'],
]
const workOrderListParamNames = ['q', 'status', 'priority', 'customer_id', 'technician_id', 'asset_id', 'date_from', 'date_to', 'work_type', 'company_code', 'open_state', 'page', 'page_size', 'sort', 'order', 'columns']
const emptyWorkOrderPage = { items: [], page: 1, page_size: 50, total: 0, pages: 1, sort: 'created_at', order: 'desc' }

export default function WorkOrders({ user, mode = 'list' }) {
  const navigate = useNavigate()
  const { workOrderId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedDetailTab = searchParams.get('tab') || 'overview'
  const detailTab = ['overview', 'assets', 'materials', 'time', 'archives', 'history'].includes(requestedDetailTab) ? requestedDetailTab : 'overview'
  const legacyLinkedWorkOrderId = searchParams.get('work_order_id')
  const linkedWorkOrderId = workOrderId || legacyLinkedWorkOrderId
  const requestedNewAssetId = searchParams.get('new_asset_id')
  const requestedMaintenance = searchParams.get('maintenance') === '1'
  const bulkCreatedCount = Number(searchParams.get('bulk_created') || 0)
  const bulkSkippedCount = Number(searchParams.get('bulk_skipped') || 0)
  const filters = {
    q: searchParams.get('q') || '',
    status: searchParams.get('status') || '',
    customer_id: searchParams.get('customer_id') || '',
    technician_id: searchParams.get('technician_id') || '',
    priority: searchParams.get('priority') || '',
    asset_id: searchParams.get('asset_id') || '',
    date_from: searchParams.get('date_from') || '',
    date_to: searchParams.get('date_to') || '',
    work_type: searchParams.get('work_type') || '',
    company_code: searchParams.get('company_code') || '',
    open_state: searchParams.get('open_state') || '',
  }
  const listPage = positiveInteger(searchParams.get('page'), 1)
  const listPageSize = allowedPageSize(searchParams.get('page_size'))
  const listSort = searchParams.get('sort') || 'created_at'
  const listOrder = searchParams.get('order') === 'asc' ? 'asc' : 'desc'
  const visibleColumns = normalizeWorkOrderColumns(searchParams.get('columns'))
  const selectedWorkOrderRef = useRef(null)
  const editorRef = useRef(null)
  const editPresenceRef = useRef({ workOrderId: null, sessionToken: null, authToken: null })
  const prefilledAssetRef = useRef(null)
  const editRouteLoadedRef = useRef(null)
  const defaultViewAppliedRef = useRef(false)
  const [orders, setOrders] = useState([])
  const [pageData, setPageData] = useState(emptyWorkOrderPage)
  const [listLoading, setListLoading] = useState(false)
  const [searchInput, setSearchInput] = useState(filters.q)
  const [savedViews, setSavedViews] = useState([])
  const [savedViewDialogOpen, setSavedViewDialogOpen] = useState(false)
  const [savedViewName, setSavedViewName] = useState('')
  const [savedViewDefault, setSavedViewDefault] = useState(false)
  const [savedViewSaving, setSavedViewSaving] = useState(false)
  const [customers, setCustomers] = useState([])
  const [locations, setLocations] = useState([])
  const [assets, setAssets] = useState([])
  const [technicians, setTechnicians] = useState([])
  const [materials, setMaterials] = useState([])
  const [contractOptions, setContractOptions] = useState([])
  const [form, setForm] = useState(empty)
  const [editing, setEditing] = useState(null)
  const [selected, setSelected] = useState(null)
  const [closeForm, setCloseForm] = useState({ work_done: '', final_status: '', labor_hours: '0', started_at: '', completed_at: '', technician_id: '', secondary_technician_id: '' })
  const [assetDerivedLocation, setAssetDerivedLocation] = useState(false)
  const [assetSelectResetKey, setAssetSelectResetKey] = useState(0)
  const [error, setError] = useState('')
  const [editSessionToken, setEditSessionToken] = useState(null)
  const [activeEditors, setActiveEditors] = useState([])
  const [selectedOrderIds, setSelectedOrderIds] = useState([])
  const [bulkPrintOrders, setBulkPrintOrders] = useState([])
  const [bulkPrintMode, setBulkPrintMode] = useState(false)
  const [bulkSelectionApplied, setBulkSelectionApplied] = useState(false)
  const [bulkEditOpen, setBulkEditOpen] = useState(false)
  const [bulkEditSubmitting, setBulkEditSubmitting] = useState(false)
  const [bulkEditForm, setBulkEditForm] = useState({ apply_status: false, status: '__unchanged__', apply_planned_date: false, planned_date: '', apply_technician: false, technician_id: '__unchanged__', apply_secondary_technician: false, secondary_technician_id: '__unchanged__' })
  const [success, setSuccess] = useState('')
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [expandedArchiveOrderIds, setExpandedArchiveOrderIds] = useState([])
  const [inlineArchives, setInlineArchives] = useState({})
  const [inlineArchiveLoading, setInlineArchiveLoading] = useState({})
  const [inlineArchiveErrors, setInlineArchiveErrors] = useState({})
  const [inlineArchiveUploadOrder, setInlineArchiveUploadOrder] = useState(null)
  const [closeArchiveUploadOpen, setCloseArchiveUploadOpen] = useState(false)
  const [detailArchiveUploadOpen, setDetailArchiveUploadOpen] = useState(false)
  const [detailArchiveRefreshKey, setDetailArchiveRefreshKey] = useState(0)

  useEffect(() => { loadBase() }, [])
  useEffect(() => {
    const customerId = form.customer_id ? Number(form.customer_id) : null
    if (!customerId) { setContractOptions([]); return }
    let active = true
    api(`/work-orders/contract-options?customer_id=${customerId}`).then(rows => { if (active) setContractOptions(rows) }).catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [form.customer_id])
  useEffect(() => { if (mode === 'list') loadOrders() }, [mode, filters.q, filters.status, filters.customer_id, filters.technician_id, filters.priority, filters.asset_id, filters.date_from, filters.date_to, filters.work_type, filters.company_code, filters.open_state, listPage, listPageSize, listSort, listOrder])
  useEffect(() => { if (mode === 'list') loadSavedViews() }, [mode])
  useEffect(() => { setSearchInput(filters.q) }, [filters.q])
  useEffect(() => {
    if (mode !== 'list' || searchInput.trim() === filters.q) return undefined
    const timeout = window.setTimeout(() => updateListParam('q', searchInput.trim()), 350)
    return () => window.clearTimeout(timeout)
  }, [mode, searchInput, filters.q])

  useEffect(() => {
    if (mode !== 'list') return
    if (legacyLinkedWorkOrderId) {
      navigate(`/work-orders/${legacyLinkedWorkOrderId}`, { replace: true })
      return
    }
    if (requestedNewAssetId) {
      const params = new URLSearchParams()
      params.set('new_asset_id', requestedNewAssetId)
      if (requestedMaintenance) params.set('maintenance', '1')
      navigate(`/work-orders/new?${params.toString()}`, { replace: true })
    }
  }, [mode, legacyLinkedWorkOrderId, requestedNewAssetId, requestedMaintenance, navigate])

  useEffect(() => {
    if (!linkedWorkOrderId || !['detail', 'edit', 'close'].includes(mode)) return undefined

    let active = true
    api(`/work-orders/${linkedWorkOrderId}`)
      .then(async (workOrder) => {
        if (!active) return
        setSelected(workOrder)
        if (mode === 'edit' && editRouteLoadedRef.current !== String(workOrder.id)) {
          editRouteLoadedRef.current = String(workOrder.id)
          await loadIntoEditor(workOrder)
        }
      })
      .catch((err) => {
        if (active) setError(err.message)
      })

    return () => { active = false }
  }, [linkedWorkOrderId, mode])

  useEffect(() => {
    if (mode !== 'detail' || !selected) return
    window.requestAnimationFrame(() => {
      selectedWorkOrderRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [mode, selected?.id])

  useEffect(() => {
    if (mode !== 'close' || !selected) return
    setCloseForm({
      work_done: selected.work_done || '',
      final_status: selected.final_status || '',
      labor_hours: selected.labor_hours ?? '0',
      started_at: toDateTimeLocalValue(selected.started_at || selected.planned_start_at || currentDateTimeLocalValue()),
      completed_at: toDateTimeLocalValue(selected.completed_at || currentDateTimeLocalValue()),
      technician_id: selected.technician_id ? String(selected.technician_id) : (user?.role?.name === 'Technikus / szerelő' ? String(user.id) : ''),
      secondary_technician_id: selected.secondary_technician_id ? String(selected.secondary_technician_id) : '',
    })
  }, [mode, selected?.id])

  useEffect(() => {
    if (mode !== 'detail' || detailTab !== 'history' || !selected?.id) return undefined
    let active = true
    setHistoryLoading(true)
    api(`/work-orders/${selected.id}/history`)
      .then((rows) => { if (active) setHistory(rows) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setHistoryLoading(false) })
    return () => { active = false }
  }, [mode, detailTab, selected?.id, selected?.version])

  useEffect(() => {
    if (mode !== 'list' || bulkSelectionApplied || !orders.length) return
    const rawSelection = sessionStorage.getItem('bulkWorkOrderSelection')
    if (!rawSelection) {
      setBulkSelectionApplied(true)
      return
    }
    try {
      const requestedIds = JSON.parse(rawSelection).map(Number).filter(Number.isFinite)
      const availableIds = new Set(orders.map((order) => order.id))
      setSelectedOrderIds(requestedIds.filter((id) => availableIds.has(id)))
    } catch {
      setSelectedOrderIds([])
    } finally {
      sessionStorage.removeItem('bulkWorkOrderSelection')
      setBulkSelectionApplied(true)
    }
  }, [mode, orders, bulkSelectionApplied])

  useEffect(() => {
    if (mode !== 'list') return undefined
    function finishBulkPrint() {
      setBulkPrintMode(false)
      setBulkPrintOrders([])
    }
    window.addEventListener('afterprint', finishBulkPrint)
    return () => window.removeEventListener('afterprint', finishBulkPrint)
  }, [mode])

  useEffect(() => {
    if (mode !== 'create' || !requestedNewAssetId || !assets.length || editing || prefilledAssetRef.current === requestedNewAssetId) return
    const asset = assets.find((row) => row.id === Number(requestedNewAssetId))
    if (!asset) return
    prefilledAssetRef.current = requestedNewAssetId
    if (!asset.customer_id) {
      setError('Ehhez az eszközhöz nincs ügyfél rendelve, ezért a munkalap nem tölthető ki automatikusan.')
      return
    }
    setForm({
      ...empty,
      customer_id: String(asset.customer_id),
      location_id: locations.some((location) => location.id === asset.current_location_id && location.is_active !== false) ? String(asset.current_location_id) : '',
      asset_ids: [asset.id],
      work_type: requestedMaintenance ? 'karbantartás' : '',
      description: requestedMaintenance ? 'Tervezett karbantartás' : '',
    })
    setAssetDerivedLocation(locations.some((location) => location.id === asset.current_location_id && location.is_active !== false))
    setAssetSelectResetKey((key) => key + 1)
  }, [mode, requestedNewAssetId, requestedMaintenance, assets, locations, editing])

  useEffect(() => {
    if (!editing || !editSessionToken) return undefined

    let active = true
    async function heartbeat() {
      try {
        const presence = await api(`/work-orders/${editing}/editing/heartbeat`, {
          method: 'POST',
          body: { session_token: editSessionToken },
        })
        if (active) setActiveEditors(presence.active_editors || [])
      } catch (err) {
        if (active) setError(`A szerkesztési jelenlét frissítése sikertelen: ${err.message}`)
      }
    }

    const interval = window.setInterval(heartbeat, 5000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [editing, editSessionToken])

  useEffect(() => {
    function releaseOnUnload() {
      const current = editPresenceRef.current
      if (!current.workOrderId || !current.sessionToken) return
      fetch(exportUrl(`/work-orders/${current.workOrderId}/editing/${current.sessionToken}`), {
        method: 'DELETE',
        credentials: 'include',
        headers: csrfHeaders(),
        keepalive: true,
      }).catch(() => {})
    }

    window.addEventListener('beforeunload', releaseOnUnload)
    return () => {
      window.removeEventListener('beforeunload', releaseOnUnload)
      releaseOnUnload()
    }
  }, [])

  async function loadBase() {
    try {
      const [cs, ls, as, ts, ms] = await Promise.all([api('/customers'), api('/locations'), api('/assets'), api('/users/technicians'), api('/materials')])
      setCustomers(cs); setLocations(ls); setAssets(as); setTechnicians(ts); setMaterials(ms)
    } catch (err) { setError(err.message) }
  }
  async function loadOrders() {
    setListLoading(true)
    try {
      const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value))
      params.set('page', String(listPage))
      params.set('page_size', String(listPageSize))
      params.set('sort', listSort)
      params.set('order', listOrder)
      const data = await api(`/work-orders/paged?${params}`)
      setPageData(data)
      setOrders(data.items || [])
      const availableIds = new Set((data.items || []).map((order) => order.id))
      setSelectedOrderIds((current) => current.filter((id) => availableIds.has(id)))
      if (data.page !== listPage) updateListParam('page', data.page > 1 ? String(data.page) : '', false)
    } catch (err) {
      setError(err.message)
    } finally {
      setListLoading(false)
    }
  }

  async function loadSavedViews() {
    try {
      const rows = await api('/work-orders/saved-views')
      setSavedViews(rows)
      const hasExplicitListState = workOrderListParamNames.some((name) => searchParams.has(name))
      if (!defaultViewAppliedRef.current && !hasExplicitListState) {
        defaultViewAppliedRef.current = true
        const defaultView = rows.find((view) => view.is_default)
        if (defaultView) applySavedView(defaultView)
      }
    } catch (err) {
      setError(err.message)
    }
  }

  function updateListParam(name, value, resetPage = true) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value !== '' && value !== null && value !== undefined) next.set(name, String(value))
      else next.delete(name)
      if (name === 'customer_id') next.delete('asset_id')
      if (resetPage && !['page', 'page_size'].includes(name)) next.delete('page')
      if (name === 'page_size') next.delete('page')
      next.delete('bulk_created')
      next.delete('bulk_skipped')
      return next
    }, { replace: true })
  }

  function resetListView() {
    setSearchInput('')
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  function changeListSort(field) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      const currentSort = next.get('sort') || 'created_at'
      const currentOrder = next.get('order') === 'asc' ? 'asc' : 'desc'
      next.set('sort', field)
      next.set('order', currentSort === field ? (currentOrder === 'asc' ? 'desc' : 'asc') : 'asc')
      next.delete('page')
      return next
    }, { replace: true })
  }

  function toggleVisibleColumn(column, checked) {
    const nextColumns = checked
      ? [...visibleColumns, column].filter((value, index, array) => array.indexOf(value) === index)
      : visibleColumns.filter((value) => value !== column)
    if (!nextColumns.includes('number')) nextColumns.unshift('number')
    updateListParam('columns', nextColumns.join(','), false)
  }

  function currentSavedViewState() {
    return {
      ...filters,
      page_size: listPageSize,
      sort: listSort,
      order: listOrder,
      columns: visibleColumns,
    }
  }

  function applySavedView(view) {
    const state = view?.state || {}
    const next = new URLSearchParams()
    workOrderListParamNames.forEach((name) => {
      if (name === 'page') return
      const value = state[name]
      if (name === 'columns' && Array.isArray(value) && value.length) next.set(name, value.join(','))
      else if (value !== '' && value !== null && value !== undefined) next.set(name, String(value))
    })
    setSearchInput(state.q || '')
    setSearchParams(next, { replace: true })
  }

  async function saveCurrentView(event) {
    event.preventDefault()
    const name = savedViewName.trim()
    if (!name) return
    setSavedViewSaving(true)
    try {
      await api('/work-orders/saved-views', {
        method: 'POST',
        body: { name, state: currentSavedViewState(), is_default: savedViewDefault },
      })
      setSavedViewDialogOpen(false)
      setSavedViewName('')
      setSavedViewDefault(false)
      setSuccess(`A(z) „${name}” nézet elmentve.`)
      await loadSavedViews()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavedViewSaving(false)
    }
  }

  async function deleteSavedView(view) {
    if (!window.confirm(`Biztosan törlöd ezt a mentett nézetet?\n\n${view.name}`)) return
    try {
      await api(`/work-orders/saved-views/${view.id}`, { method: 'DELETE' })
      setSavedViews((current) => current.filter((item) => item.id !== view.id))
    } catch (err) {
      setError(err.message)
    }
  }

  async function releaseEditPresence() {
    const current = editPresenceRef.current
    editPresenceRef.current = { workOrderId: null, sessionToken: null, authToken: null }
    setEditSessionToken(null)
    setActiveEditors([])
    if (!current.workOrderId || !current.sessionToken) return
    try {
      await api(`/work-orders/${current.workOrderId}/editing/${current.sessionToken}`, { method: 'DELETE' })
    } catch {
      // A session rövid időn belül automatikusan lejár, ezért a kilépést nem blokkoljuk.
    }
  }

  async function startEditPresence(workOrderId) {
    const presence = await api(`/work-orders/${workOrderId}/editing/start`, { method: 'POST' })
    editPresenceRef.current = { workOrderId, sessionToken: presence.session_token }
    setEditSessionToken(presence.session_token)
    setActiveEditors(presence.active_editors || [])
  }

  const formCustomerId = form.customer_id ? Number(form.customer_id) : null
  const formLocationId = form.location_id ? Number(form.location_id) : null
  const formLocations = locations.filter((location) => (
    formCustomerId
    && location.customer_id === formCustomerId
    && (location.is_active !== false || (editing && location.id === formLocationId))
  ))
  const formAssets = assets.filter((asset) => assetMatches(asset, formCustomerId, formLocationId))
  const selectedCustomer = customers.find((customer) => customer.id === formCustomerId)
  const selectedLocation = locations.find((location) => location.id === formLocationId)
  const formContacts = (selectedCustomer?.contacts || []).filter((contact) => !formLocationId || !contact.location_id || contact.location_id === formLocationId)
  const selectedContact = formContacts.find((contact) => contact.id === Number(form.contact_id))
  const selectedAssets = assets.filter((asset) => form.asset_ids.map(Number).includes(asset.id))
  const availableContractOptions = contractOptions.filter((contract) => {
    const locationOk = !contract.location_ids?.length || (formLocationId && contract.location_ids.includes(formLocationId))
    const assetIds = form.asset_ids.map(Number)
    const assetsOk = !contract.asset_ids?.length || !assetIds.length || assetIds.every((id) => contract.asset_ids.includes(id))
    return locationOk && assetsOk
  })
  const selectedContract = contractOptions.find((contract) => contract.id === Number(form.contract_id))
  const filterCustomerId = filters.customer_id ? Number(filters.customer_id) : null
  const filterAssetOptions = assets.filter((asset) => !filterCustomerId || asset.customer_id === filterCustomerId)

  function assetMatches(asset, customerId, locationId = null) {
    if (!customerId || asset.customer_id !== customerId) return false
    if (locationId && asset.current_location_id && asset.current_location_id !== locationId) return false
    return true
  }

  function cleanAssetIdsFor(ids, customerId, locationId = null) {
    return (ids || [])
      .map(Number)
      .filter((id) => {
        const asset = assets.find((candidate) => candidate.id === id)
        return asset && assetMatches(asset, customerId, locationId)
      })
  }

  function setField(k, v) { setForm((p) => ({ ...p, [k]: v })) }
  function addMaterialLine() { setForm((current) => ({ ...current, materials: [...(current.materials || []), emptyMaterialLine()] })) }
  function updateMaterialLine(index, field, value) {
    setForm((current) => ({ ...current, materials: (current.materials || []).map((line, lineIndex) => lineIndex === index ? { ...line, [field]: value } : line) }))
  }
  function removeMaterialLine(index) { setForm((current) => ({ ...current, materials: (current.materials || []).filter((_, lineIndex) => lineIndex !== index) })) }

  function handleCustomerChange(value) {
    const nextCustomerId = value ? Number(value) : null
    setAssetDerivedLocation(false)
    setForm((previous) => {
      const allowedLocations = locations.filter((location) => nextCustomerId && location.customer_id === nextCustomerId && location.is_active !== false)
      const currentLocationAllowed = previous.location_id && allowedLocations.some((location) => location.id === Number(previous.location_id))
      const nextLocationId = currentLocationAllowed ? previous.location_id : (allowedLocations.length === 1 ? String(allowedLocations[0].id) : '')
      const nextCustomer = customers.find((customer) => customer.id === nextCustomerId)
      const contactAllowed = nextCustomer?.contacts?.some((contact) => String(contact.id) === previous.contact_id && (!nextLocationId || !contact.location_id || String(contact.location_id) === String(nextLocationId)))
      return {
        ...previous,
        customer_id: value,
        location_id: nextLocationId,
        contact_id: contactAllowed ? previous.contact_id : '',
        contract_id: '',
        contract_type: '',
        asset_ids: cleanAssetIdsFor(previous.asset_ids, nextCustomerId, nextLocationId ? Number(nextLocationId) : null),
      }
    })
  }

  function handleLocationChange(value) {
    setAssetDerivedLocation(false)
    const selected = locations.find((location) => location.id === Number(value))
    const nextCustomerId = selected?.customer_id || formCustomerId
    setForm((previous) => ({
      ...previous,
      customer_id: nextCustomerId ? String(nextCustomerId) : previous.customer_id,
      location_id: value,
      contact_id: (selectedCustomer?.contacts || []).some((contact) => String(contact.id) === previous.contact_id && (!value || !contact.location_id || String(contact.location_id) === String(value))) ? previous.contact_id : '',
      contract_id: '',
      contract_type: '',
      asset_ids: cleanAssetIdsFor(previous.asset_ids, nextCustomerId, value ? Number(value) : null),
    }))
  }
  function normalize() {
    const materialLines = (form.materials || []).filter((line) => line.material_id || line.quantity || line.unit_price || line.note)
    const incompleteLine = materialLines.find((line) => !line.material_id || !line.quantity || Number(line.quantity) <= 0)
    if (incompleteLine) throw new Error('Minden anyagsornál válassz cikket és adj meg nullánál nagyobb mennyiséget.')
    const technicianId = form.technician_id ? Number(form.technician_id) : null
    const secondaryTechnicianId = form.secondary_technician_id ? Number(form.secondary_technician_id) : null
    if (technicianId && technicianId === secondaryTechnicianId) throw new Error('Ugyanaz a technikus nem választható ki kétszer.')
    return {
      customer_id: Number(form.customer_id),
      location_id: form.location_id ? Number(form.location_id) : null,
      contact_id: form.contact_id ? Number(form.contact_id) : null,
      contract_id: form.contract_id ? Number(form.contract_id) : null,
      asset_ids: form.asset_ids.map(Number),
      description: form.description,
      priority: form.priority,
      status: form.status,
      technician_id: technicianId,
      secondary_technician_id: secondaryTechnicianId,
      planned_date: form.planned_date || (form.planned_start_at ? form.planned_start_at.slice(0, 10) : null),
      planned_start_at: form.planned_start_at || null,
      planned_end_at: form.planned_end_at || null,
      started_at: form.started_at || null,
      completed_at: form.completed_at || null,
      work_done: form.work_done || null,
      labor_hours: form.labor_hours === '' ? null : Number(form.labor_hours),
      work_type: form.work_type || null,
      contract_type: selectedContract?.contract_type || form.contract_type.trim() || null,
      internal_note: form.internal_note || null,
      customer_note: null,
      materials: materialLines.map((line) => ({ material_id: Number(line.material_id), quantity: Number(line.quantity), unit_price: line.unit_price === '' ? null : Number(line.unit_price), note: line.note || null })),
    }
  }
  async function submit(e) {
    e.preventDefault(); setError('')
    try {
      const payload = normalize()
      let saved
      if (editing) {
        payload.version = Number(form.version)
        saved = await api(`/work-orders/${editing}`, { method: 'PUT', body: payload })
      } else {
        saved = await api('/work-orders', { method: 'POST', body: payload })
      }
      await releaseEditPresence()
      setForm(empty)
      setEditing(null)
      setAssetDerivedLocation(false)
      navigate(`/work-orders/${saved.id}`)
    } catch (err) {
      if (err.status === 409 && editing) {
        try {
          const latest = await api(`/work-orders/${editing}`)
          await loadIntoEditor(latest)
          if (selected?.id === latest.id) setSelected(latest)
          setError(`${err.message} A legfrissebb változatot betöltöttük a szerkesztőbe.`)
        } catch {
          setError(err.message)
        }
      } else {
        setError(err.message)
      }
    }
  }
  async function loadIntoEditor(row) {
    if (editPresenceRef.current.workOrderId && editPresenceRef.current.workOrderId !== row.id) {
      await releaseEditPresence()
    }
    setEditing(row.id)
    setAssetDerivedLocation(false)
    setForm({
      ...empty,
      ...row,
      customer_id: row.customer_id || '', location_id: row.location_id || '', contact_id: row.contact_id || '', contract_id: row.contract_id || '', technician_id: row.technician_id || '', secondary_technician_id: row.secondary_technician_id || '',
      asset_ids: row.asset_ids || [], planned_date: row.planned_date || '', planned_start_at: toDateTimeLocalValue(row.planned_start_at), planned_end_at: toDateTimeLocalValue(row.planned_end_at), started_at: toDateTimeLocalValue(row.started_at), completed_at: toDateTimeLocalValue(row.completed_at),
      labor_hours: row.labor_hours ?? '', work_type: row.work_type ?? '', contract_type: row.contract_type ?? '',
      materials: (row.materials || []).map((line) => ({ material_id: String(line.material_id), quantity: String(line.quantity), unit_price: line.unit_price === null || line.unit_price === undefined ? '' : String(line.unit_price), note: line.note || '' })),
    })
    window.requestAnimationFrame(() => {
      editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    if (editPresenceRef.current.workOrderId === row.id && editPresenceRef.current.sessionToken) return
    try {
      await startEditPresence(row.id)
    } catch (err) {
      setError(`A munkalap megnyílt, de a párhuzamos szerkesztés ellenőrzése sikertelen: ${err.message}`)
    }
  }

  async function leaveEditMode() {
    await releaseEditPresence()
    const previousId = editing
    setEditing(null)
    setForm(empty)
    setAssetDerivedLocation(false)
    navigate(previousId ? `/work-orders/${previousId}` : '/work-orders')
  }
  async function cancel(row) {
    if (!confirm('Biztosan sztornózod a munkalapot?')) return
    setError('')
    try {
      await api(`/work-orders/${row.id}?version=${encodeURIComponent(row.version)}`, { method: 'DELETE' })
      if (mode === 'list') {
        await loadOrders()
      } else {
        navigate('/work-orders')
      }
    } catch (err) {
      setError(err.message)
      if (err.status === 409 && mode === 'list') await loadOrders()
    }
  }
  async function close(row, event = null) {
    event?.preventDefault?.()
    setError('')
    try {
      const closed = await api(`/work-orders/${row.id}/close`, {
        method: 'POST',
        body: {
          version: Number(row.version),
          work_done: closeForm.work_done,
          final_status: closeForm.final_status,
          labor_hours: Number(closeForm.labor_hours),
          started_at: closeForm.started_at || null,
          completed_at: closeForm.completed_at || currentDateTimeLocalValue(),
          technician_id: closeForm.technician_id ? Number(closeForm.technician_id) : null,
          secondary_technician_id: closeForm.secondary_technician_id ? Number(closeForm.secondary_technician_id) : null,
        },
      })
      setCloseForm({ work_done: '', final_status: '', labor_hours: '0', started_at: '', completed_at: '', technician_id: '', secondary_technician_id: '' })
      setSelected(closed)
      navigate(`/work-orders/${closed.id}`)
    } catch (err) {
      setError(err.message)
      if (err.status === 409) {
        try {
          const latest = await api(`/work-orders/${row.id}`)
          setSelected(latest)
        } catch {
          // Az eredeti ütközési üzenet marad látható.
        }
      }
    }
  }
  function clearAssetSelection() {
    setForm((previous) => ({
      ...previous,
      asset_ids: [],
      // A kapcsolódó eszközlista alapállapota az ügyfél szerinti teljes lista.
      // Ehhez a helyszínszűrőt is törölni kell, mert a lista ebből számolódik.
      location_id: '',
      contract_id: '',
      contract_type: '',
    }))
    setAssetDerivedLocation(false)
    setAssetSelectResetKey((key) => key + 1)
  }

  function onAssetsChange(e) {
    const selectedIds = Array.from(e.target.selectedOptions).map((option) => Number(option.value))
    const selected = selectedIds.map((id) => assets.find((asset) => asset.id === id)).filter(Boolean)
    if (!selected.length) {
      clearAssetSelection()
      return
    }
    const first = selected[0]
    const nextCustomerId = formCustomerId || first.customer_id
    const sharedLocationId = selected.every((asset) => asset.current_location_id === first.current_location_id) ? first.current_location_id : null
    const selectableSharedLocationId = locations.some((location) => location.id === sharedLocationId && location.is_active !== false) ? sharedLocationId : null
    const locationWasEmpty = !formLocationId
    const nextLocationId = formLocationId || selectableSharedLocationId || ''
    const locationFilledFromAsset = Boolean(locationWasEmpty && selectableSharedLocationId)
    const nextIds = selected
      .filter((asset) => assetMatches(asset, nextCustomerId, nextLocationId ? Number(nextLocationId) : null))
      .map((asset) => asset.id)
    setAssetDerivedLocation(locationFilledFromAsset)
    setForm((previous) => {
      const nextLocationValue = nextLocationId ? String(nextLocationId) : previous.location_id
      const nextCustomer = customers.find((customer) => customer.id === nextCustomerId)
      const contactAllowed = nextCustomer?.contacts?.some((contact) => String(contact.id) === previous.contact_id && (!nextLocationValue || !contact.location_id || String(contact.location_id) === String(nextLocationValue)))
      return {
        ...previous,
        customer_id: nextCustomerId ? String(nextCustomerId) : previous.customer_id,
        location_id: nextLocationValue,
        contact_id: contactAllowed ? previous.contact_id : '',
        contract_id: '',
        contract_type: '',
        asset_ids: nextIds,
      }
    })
  }
  function select(row) {
    navigate(`/work-orders/${row.id}`)
  }

  function openEdit(row) {
    navigate(`/work-orders/${row.id}/edit`)
  }
  async function downloadCsv() {
    const response = await fetch(exportUrl('/export/work-orders.csv'), { credentials: 'include' })
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'munkalapok.csv'; a.click(); URL.revokeObjectURL(url)
  }


  function toggleOrderSelection(orderId, checked) {
    setSelectedOrderIds((current) => checked
      ? Array.from(new Set([...current, orderId]))
      : current.filter((id) => id !== orderId))
  }

  function toggleAllOrders(orderIds, checked) {
    setSelectedOrderIds((current) => {
      if (checked) return Array.from(new Set([...current, ...orderIds]))
      const removed = new Set(orderIds)
      return current.filter((id) => !removed.has(id))
    })
  }

  function openBulkEdit() {
    const selectedSet = new Set(selectedOrderIds)
    const selectedRows = orders.filter((order) => selectedSet.has(order.id))
    if (!selectedRows.length) {
      setError('Jelölj ki legalább egy munkalapot a tömeges szerkesztéshez.')
      return
    }
    const selectedStatuses = new Set(selectedRows.map((order) => order.status || ''))
    const plannedDates = new Set(selectedRows.map((order) => order.planned_date || ''))
    const technicianIds = new Set(selectedRows.map((order) => order.technician_id === null || order.technician_id === undefined ? '__none__' : String(order.technician_id)))
    const secondaryTechnicianIds = new Set(selectedRows.map((order) => order.secondary_technician_id === null || order.secondary_technician_id === undefined ? '__none__' : String(order.secondary_technician_id)))
    setError('')
    setSuccess('')
    setBulkEditForm({
      apply_status: false,
      status: selectedStatuses.size === 1 ? [...selectedStatuses][0] : '__unchanged__',
      apply_planned_date: false,
      planned_date: plannedDates.size === 1 ? [...plannedDates][0] : '',
      apply_technician: false,
      technician_id: technicianIds.size === 1 ? [...technicianIds][0] : '__unchanged__',
      apply_secondary_technician: false,
      secondary_technician_id: secondaryTechnicianIds.size === 1 ? [...secondaryTechnicianIds][0] : '__unchanged__',
    })
    setBulkEditOpen(true)
  }

  async function submitBulkEdit(event) {
    event.preventDefault()
    if (!bulkEditForm.apply_status && !bulkEditForm.apply_planned_date && !bulkEditForm.apply_technician && !bulkEditForm.apply_secondary_technician) {
      setError('Válassz legalább egy tömegesen módosítandó mezőt.')
      return
    }
    if (bulkEditForm.apply_status && bulkEditForm.status === '__unchanged__') {
      setError('Válassz státuszt a kijelölt munkalapokhoz.')
      return
    }
    if (bulkEditForm.apply_planned_date && !bulkEditForm.planned_date) {
      setError('Add meg a minden kijelölt munkalapra érvényes tervezett napot.')
      return
    }
    if (bulkEditForm.apply_technician && bulkEditForm.technician_id === '__unchanged__') {
      setError('Válassz elsődleges technikust, vagy válaszd a „Nincs kijelölve” értéket.')
      return
    }
    if (bulkEditForm.apply_secondary_technician && bulkEditForm.secondary_technician_id === '__unchanged__') {
      setError('Válassz második technikust, vagy válaszd a „Nincs kijelölve” értéket.')
      return
    }

    const selectedSet = new Set(selectedOrderIds)
    const selectedRows = orders.filter((order) => selectedSet.has(order.id))
    if (!selectedRows.length) {
      setError('A kijelölt munkalapok már nem találhatók az aktuális listában.')
      setBulkEditOpen(false)
      return
    }

    setBulkEditSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const result = await api('/work-orders/bulk-update', {
        method: 'POST',
        body: {
          items: selectedRows.map((order) => ({ id: order.id, version: Number(order.version) })),
          apply_status: bulkEditForm.apply_status,
          status: bulkEditForm.apply_status ? bulkEditForm.status : null,
          apply_planned_date: bulkEditForm.apply_planned_date,
          planned_date: bulkEditForm.apply_planned_date ? bulkEditForm.planned_date : null,
          apply_technician: bulkEditForm.apply_technician,
          technician_id: bulkEditForm.apply_technician
            ? (bulkEditForm.technician_id === '__none__' ? null : Number(bulkEditForm.technician_id))
            : null,
          apply_secondary_technician: bulkEditForm.apply_secondary_technician,
          secondary_technician_id: bulkEditForm.apply_secondary_technician
            ? (bulkEditForm.secondary_technician_id === '__none__' ? null : Number(bulkEditForm.secondary_technician_id))
            : null,
        },
      })
      setBulkEditOpen(false)
      setSuccess(`${result.updated_count} munkalap tömeges módosítása sikeres.`)
      await loadOrders()
      if (selected && selectedSet.has(selected.id)) setSelected(await api(`/work-orders/${selected.id}`))
    } catch (err) {
      setError(err.status === 409 ? `${err.message} A tömeges módosítás egyetlen munkalapon sem került végrehajtásra.` : err.message)
      if (err.status === 409) await loadOrders()
    } finally {
      setBulkEditSubmitting(false)
    }
  }

  function printSelectedOrders() {
    const selectedSet = new Set(selectedOrderIds)
    const printable = orders.filter((order) => selectedSet.has(order.id))
    if (!printable.length) {
      setError('Jelölj ki legalább egy munkalapot a tömeges nyomtatáshoz.')
      return
    }
    setError('')
    setBulkPrintOrders(printable)
    setBulkPrintMode(true)
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => window.print())
    })
  }

  function printSingleOrder() {
    setBulkPrintMode(false)
    setBulkPrintOrders([])
    window.requestAnimationFrame(() => window.print())
  }

  function handleFilterCustomerChange(value) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set('customer_id', value)
      else next.delete('customer_id')
      next.delete('asset_id')
      next.delete('page')
      return next
    }, { replace: true })
  }

  async function loadInlineArchives(orderId, force = false) {
    if (!force && Object.prototype.hasOwnProperty.call(inlineArchives, orderId)) return
    setInlineArchiveLoading((current) => ({ ...current, [orderId]: true }))
    setInlineArchiveErrors((current) => ({ ...current, [orderId]: '' }))
    try {
      const rows = await api(`/work-orders/${orderId}/archives`)
      setInlineArchives((current) => ({ ...current, [orderId]: rows }))
    } catch (err) {
      setInlineArchiveErrors((current) => ({ ...current, [orderId]: err.message }))
    } finally {
      setInlineArchiveLoading((current) => ({ ...current, [orderId]: false }))
    }
  }

  function toggleInlineArchive(row, expanded) {
    setExpandedArchiveOrderIds((current) => expanded
      ? [...new Set([...current, row.id])]
      : current.filter((id) => id !== row.id))
    if (expanded) loadInlineArchives(row.id)
  }

  function renderInlineArchive(row) {
    return <section className="work-order-inline-archive" aria-label={`${row.number} archívuma`}>
      <div className="section-title-row"><div><h3>Archívum – {row.number}</h3><p className="muted">A munkalaphoz feltöltött beszkennelt vagy digitális fájlok.</p></div><button type="button" disabled={Boolean(inlineArchiveLoading[row.id])} onClick={() => setInlineArchiveUploadOrder(row)}>Fájl archiválása</button></div>
      {inlineArchiveErrors[row.id] && <div className="error">{inlineArchiveErrors[row.id]}</div>}
      <WorkOrderArchiveTable archives={inlineArchives[row.id] || []} loading={Boolean(inlineArchiveLoading[row.id])} emptyText="Ehhez a munkalaphoz még nincs archív fájl." user={user} onDeleted={(deleted) => setInlineArchives((current) => ({ ...current, [row.id]: (current[row.id] || []).filter((item) => item.id !== deleted.id) }))} />
    </section>
  }

  const companyCodes = [...new Set([...customers.map((customer) => customer.company_code), ...assets.map((asset) => asset.company_code)].filter(Boolean))].sort((a, b) => a.localeCompare(b, 'hu'))
  const activeListFilterCount = Object.values(filters).filter(Boolean).length
  const searchPending = searchInput.trim() !== filters.q
  const listColumns = [
    { id: 'number', key: 'number', sortKey: 'number', label: 'Munkalap', render: (row) => <div className="work-order-cell"><strong>{row.number}</strong><small>{workTypeLabel(row.work_type)} · {row.priority}</small></div> },
    { id: 'status', key: 'status', sortKey: 'status', label: 'Státusz', render: (row) => <span className={`work-order-status-badge status-${statusSlug(row.status)}`}>{row.status}</span> },
    { id: 'priority', key: 'priority', sortKey: 'priority', label: 'Prioritás', render: (row) => <span className={`priority-badge priority-${statusSlug(row.priority)}`}>{row.priority}</span> },
    { id: 'customer', key: 'customer_name', sortKey: 'customer_name', label: 'Ügyfél', render: (row) => <div className="work-order-cell"><strong>{row.customer_name || '-'}</strong><small>{row.customer_company_code || ''}</small></div> },
    { id: 'location', key: 'location_name', sortKey: 'location_name', label: 'Helyszín', render: (row) => <div className="work-order-cell"><strong>{row.location_name || '-'}</strong><small>{row.location_address || ''}</small></div> },
    { id: 'assets', key: 'assets', label: 'Gép / gyári szám', sortable: false, render: (row) => <WorkOrderAssetListCell assets={row.assets} /> },
    { id: 'description', key: 'description', sortKey: 'description', label: 'Feladat', render: (row) => <span className="two-line-text" title={row.description}>{row.description}</span> },
    { id: 'technician', key: 'technician_name', sortKey: 'technician_name', label: 'Technikus', render: (row) => technicianDisplay(row) },
    { id: 'planned', key: 'planned_date', sortKey: 'planned_date', label: 'Tervezett idő', render: (row) => formatDate(row.planned_start_at || row.planned_date) },
    { id: 'work_type', key: 'work_type', sortKey: 'work_type', label: 'Munka típusa', render: (row) => workTypeLabel(row.work_type) },
    { id: 'created_at', key: 'created_at', sortKey: 'created_at', label: 'Létrehozva', render: (row) => formatDate(row.created_at) },
    { id: 'updated_at', key: 'updated_at', sortKey: 'updated_at', label: 'Módosítva', render: (row) => formatDate(row.updated_at) },
  ].filter((column) => visibleColumns.includes(column.id))

  const feedback = <>
    {error && <div className="error no-print">{error}</div>}
    {success && <div className="success no-print">{success}</div>}
  </>

  const editorPanel = (
    <div ref={editorRef} className="panel work-order-editor-panel no-print">
      <h2>{editing ? `Munkalap szerkesztése${selected?.number ? ` – ${selected.number}` : ''}` : 'Új munkalap'}</h2>
      {editing && activeEditors.length > 0 && <div className="edit-presence-warning" role="alert"><strong>Figyelem: ezt a munkalapot másik felhasználó is szerkeszti.</strong><span>{activeEditors.map((editor) => `${editor.full_name} (${editor.email})`).join(', ')}</span><small>A mentéskori verzióellenőrzés megakadályozza a csendes felülírást, de egyeztessetek a módosításokról.</small></div>}
      <form className="grid-form work-order-form" onSubmit={submit}>
        <Field label="Ügyfél"><select value={form.customer_id} onChange={(e) => handleCustomerChange(e.target.value)} required><option value="">Válassz ügyfelet</option>{customers.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Helyszín"><select value={form.location_id || ''} onChange={(e) => handleLocationChange(e.target.value)} disabled={!form.customer_id}><option value="">Nincs / később megadva</option>{formLocations.map(l => <option value={l.id} key={l.id}>{l.name} - {l.address || 'nincs cím'}{l.is_active === false ? ' · inaktív (meglévő)' : ''}</option>)}</select></Field>
        <Field label="Kapcsolattartó"><select value={form.contact_id || ''} onChange={(e) => setField('contact_id', e.target.value)} disabled={!form.customer_id}><option value="">Automatikus / nincs kiválasztva</option>{formContacts.map(contact => <option value={contact.id} key={contact.id}>{contact.category} - {contact.name}{contact.location_name ? ` - ${contact.location_name}` : ''}{contact.is_primary ? ' - elsődleges' : ''}</option>)}</select></Field>
        <Field label="Kapcsolódó eszközök">
          <select key={assetSelectResetKey} multiple value={form.asset_ids.map(String)} onChange={onAssetsChange} disabled={!form.customer_id}>{formAssets.map(a => <option value={a.id} key={a.id}>{assetLabel(a)}</option>)}</select>
          <div className="field-actions"><button type="button" className="secondary" onClick={clearAssetSelection} disabled={!form.asset_ids.length && !form.location_id}>Eszközválasztás törlése</button></div>
          <small>{form.customer_id ? (form.location_id ? 'A lista a kiválasztott ügyfélre és helyszínre van szűrve. Törlés után az ügyfél teljes eszközlistája jelenik meg.' : 'A lista a kiválasztott ügyfél teljes eszközlistáját mutatja.') : 'Először válassz ügyfelet.'}</small>
        </Field>
        {(selectedCustomer || selectedLocation || selectedAssets.length > 0) && <div className="linked-data-card">
          <strong>Kapcsolt adatok az importált sor logikája szerint</strong>
          <p><span>Ügyfél:</span> {selectedCustomer?.name || '-'}</p>
          <p><span>Cím:</span> {selectedLocation?.address || selectedCustomer?.address || '-'}</p>
          <p><span>Kapcsolattartó:</span> {selectedContact?.name || selectedCustomer?.contact_person || '-'}</p>
          <p><span>Kapcsolattartó típusa:</span> {selectedContact?.category || '-'}</p>
          <p><span>Telefon:</span> {selectedContact?.phone || selectedCustomer?.phone || '-'}</p>
          <p><span>E-mail:</span> {selectedContact?.email || selectedCustomer?.email || '-'}</p>
          <p><span>Eszköz:</span> {selectedAssets.map(assetLabel).join(', ') || '-'}</p>
        </div>}
        <Field label="Prioritás"><select value={form.priority} onChange={(e) => setField('priority', e.target.value)}>{priorities.map(p => <option key={p}>{p}</option>)}</select></Field>
        <Field label="Státusz"><select value={form.status} onChange={(e) => setField('status', e.target.value)}>{statuses.map(s => <option key={s}>{s}</option>)}</select></Field>
        <Field label="Elsődleges technikus"><select value={form.technician_id || ''} onChange={(e) => setField('technician_id', e.target.value)}><option value="">Nincs kijelölve</option>{technicians.map(t => <option value={t.id} key={t.id} disabled={String(t.id) === String(form.secondary_technician_id)}>{t.full_name}</option>)}</select></Field>
        <Field label="Második technikus"><select value={form.secondary_technician_id || ''} onChange={(e) => setField('secondary_technician_id', e.target.value)}><option value="">Nincs kijelölve</option>{technicians.map(t => <option value={t.id} key={t.id} disabled={String(t.id) === String(form.technician_id)}>{t.full_name}</option>)}</select></Field>
        <Field label="Tervezett nap"><input type="date" value={form.planned_date || ''} onChange={(e) => setField('planned_date', e.target.value)} /></Field>
        <Field label="Tervezett kezdés"><input type="datetime-local" value={form.planned_start_at || ''} onChange={(e) => setForm((previous) => ({ ...previous, planned_start_at: e.target.value, planned_date: e.target.value ? e.target.value.slice(0, 10) : previous.planned_date }))} /></Field>
        <Field label="Tervezett befejezés"><input type="datetime-local" value={form.planned_end_at || ''} min={form.planned_start_at || undefined} onChange={(e) => setField('planned_end_at', e.target.value)} /></Field>
        <Field label="Tényleges kezdés"><input type="datetime-local" value={form.started_at || ''} onChange={(e) => setField('started_at', e.target.value)} /></Field>
        <Field label="Tényleges befejezés"><input type="datetime-local" value={form.completed_at || ''} min={form.started_at || undefined} onChange={(e) => setField('completed_at', e.target.value)} /></Field>
        <Field label="Munkaidő"><input type="number" step="0.25" value={form.labor_hours ?? ''} onChange={(e) => setField('labor_hours', e.target.value)} /></Field>
        <Field label="Munka típusa"><select value={form.work_type || ''} onChange={(e) => setField('work_type', e.target.value)}><option value="">Nincs megadva</option>{workTypes.map(type => <option value={type} key={type}>{workTypeLabel(type)}</option>)}</select></Field>
        <Field label="CRM szerződés"><select value={form.contract_id || ''} onChange={(e) => { const id = e.target.value; const contract = contractOptions.find(row => String(row.id) === String(id)); setForm(previous => ({ ...previous, contract_id: id, contract_type: contract?.contract_type || previous.contract_type })) }} disabled={!form.customer_id}><option value="">Nincs szerződéshez kötve</option>{availableContractOptions.map(contract => <option value={contract.id} key={contract.id} disabled={contract.status !== 'aktív' && String(contract.id) !== String(form.contract_id)}>{contract.contract_number} — {contract.contract_type} ({contract.status})</option>)}</select><small>{form.customer_id ? 'A lista a kiválasztott ügyfél, helyszín és eszközök alapján szűrhető.' : 'Először válassz ügyfelet.'}</small></Field>
        <Field label="Szerződés típusa"><input maxLength="120" value={form.contract_type || ''} readOnly={!!selectedContract} onChange={(e) => setField('contract_type', e.target.value)} placeholder="Szerződés típusa" /></Field>
        <Field label="Hiba / feladat leírása"><textarea value={form.description} onChange={(e) => setField('description', e.target.value)} required /></Field>
        <Field label="Elvégzett munka"><textarea value={form.work_done || ''} onChange={(e) => setField('work_done', e.target.value)} /></Field>
        <Field label="Belső megjegyzés"><textarea value={form.internal_note || ''} onChange={(e) => setField('internal_note', e.target.value)} /></Field>
        <section className="work-order-material-editor">
          <div className="section-title-row"><div><h3>Felhasznált anyagok</h3><p className="muted">Tetszőleges számú cikk rögzíthető a munkalaphoz.</p></div><button type="button" className="secondary" onClick={addMaterialLine}>+ Anyagsor</button></div>
          {!form.materials?.length && <p className="muted material-empty-state">Nincs felhasznált anyag rögzítve.</p>}
          {(form.materials || []).map((line, index) => <div className="work-order-material-line" key={`material-${index}`}>
            <Field label={`Cikk ${index + 1}`}><select value={line.material_id || ''} onChange={(event) => updateMaterialLine(index, 'material_id', event.target.value)} required><option value="">Válassz cikket</option>{materials.map((material) => <option value={material.id} key={material.id}>{material.sku} - {material.name}</option>)}</select></Field>
            <Field label="Mennyiség"><input type="number" min="0.01" step="0.01" value={line.quantity || ''} onChange={(event) => updateMaterialLine(index, 'quantity', event.target.value)} required /></Field>
            <Field label="Egységár"><input type="number" min="0" step="0.01" value={line.unit_price ?? ''} onChange={(event) => updateMaterialLine(index, 'unit_price', event.target.value)} placeholder="Törzsadat szerinti" /></Field>
            <Field label="Megjegyzés"><input value={line.note || ''} onChange={(event) => updateMaterialLine(index, 'note', event.target.value)} /></Field>
            <button type="button" className="danger secondary material-remove-button" onClick={() => removeMaterialLine(index)}>Sor törlése</button>
          </div>)}
        </section>
        <div className="sticky-form-actions"><button type="button" className="secondary" onClick={leaveEditMode}>Mégse</button><button type="submit">{editing ? 'Módosítások mentése' : 'Munkalap létrehozása'}</button></div>
      </form>
      {editing && selected && <WorkOrderPrinterService order={selected} materials={materials} meterOnly />}
    </div>
  )

  if (mode === 'create' || mode === 'edit') {
    return (
      <section className="work-order-form-page">
        <div className="page-head no-print"><div><button type="button" className="link-button" onClick={leaveEditMode}>← Vissza</button><h1>{mode === 'edit' ? 'Munkalap szerkesztése' : 'Új munkalap'}</h1></div></div>
        {feedback}
        {mode === 'edit' && !editing && !error ? <div className="panel">Munkalap betöltése...</div> : editorPanel}
      </section>
    )
  }

  if (mode === 'close') {
    return (
      <section className="work-order-close-page">
        <div className="work-order-breadcrumb no-print"><button type="button" className="link-button" onClick={() => navigate(selected ? `/work-orders/${selected.id}` : '/work-orders')}>← Vissza a munkalaphoz</button></div>
        {feedback}
        {!selected && !error && <div className="panel">Munkalap betöltése...</div>}
        {selected && ['lezárva', 'törölve / sztornózva'].includes(selected.status) && <div className="panel"><h1>{selected.number}</h1><p>Ez a munkalap {selected.status === 'lezárva' ? 'már le van zárva' : 'sztornózva van'}, ezért nem zárható le.</p><button onClick={() => navigate(`/work-orders/${selected.id}`)}>Munkalap megnyitása</button></div>}
        {selected && !['lezárva', 'törölve / sztornózva'].includes(selected.status) && (
          <>
            <WorkOrderClosePage
              order={selected}
              technicians={technicians}
              form={closeForm}
              setForm={setCloseForm}
              onSubmit={(event) => close(selected, event)}
              onCancel={() => navigate(`/work-orders/${selected.id}`)}
              onArchiveUpload={() => setCloseArchiveUploadOpen(true)}
            />
            <WorkOrderPrinterService order={selected} materials={materials} />
            {closeArchiveUploadOpen && <WorkOrderArchiveUploadModal
              targetType="workOrder"
              targetId={selected.id}
              title={`${selected.number} beszkennelt munkalapja`}
              defaultSourceNumber={selected.number}
              defaultWorkDate={closeForm.completed_at || selected.completed_at || selected.planned_date}
              onClose={() => setCloseArchiveUploadOpen(false)}
              onSaved={(created) => { setCloseArchiveUploadOpen(false); setSuccess(`${created.archive_number} sikeresen archiválva a munkalaphoz.`) }}
            />}
          </>
        )}
      </section>
    )
  }

  if (mode === 'detail') {
    return (
      <section className="work-order-detail-page">
        <div className="work-order-breadcrumb no-print"><button type="button" className="link-button" onClick={() => navigate('/work-orders')}>← Vissza a munkalapokhoz</button></div>
        {feedback}
        {!selected && !error && <div className="panel">Munkalap betöltése...</div>}
        {selected && <div ref={selectedWorkOrderRef} className="selected-work-order-anchor single-print-content">
          <WorkOrderDetailPage
            order={selected}
            user={user}
            tab={detailTab}
            history={history}
            historyLoading={historyLoading}
            materialsCatalog={materials}
            onTabChange={(tab) => navigate(`/work-orders/${selected.id}?tab=${tab}`, { replace: true })}
            onEdit={() => openEdit(selected)}
            onClose={() => navigate(`/work-orders/${selected.id}/close`)}
            onArchive={() => setDetailArchiveUploadOpen(true)}
            onPrint={printSingleOrder}
            onAssetOpen={(assetId) => navigate(`/assets/${assetId}`)}
            archiveRefreshKey={detailArchiveRefreshKey}
          />
          <div className="detail-print-copy"><PrintableWorkOrder order={selected} /></div>
        </div>}
        {selected && detailArchiveUploadOpen && <WorkOrderArchiveUploadModal
          targetType="workOrder"
          targetId={selected.id}
          title={`${selected.number} archiválása`}
          defaultSourceNumber={selected.number}
          defaultWorkDate={selected.completed_at || selected.planned_date}
          onClose={() => setDetailArchiveUploadOpen(false)}
          onSaved={(created) => {
            setDetailArchiveUploadOpen(false)
            setSuccess(`${created.archive_number} sikeresen archiválva a munkalaphoz.`)
            setDetailArchiveRefreshKey((value) => value + 1)
          }}
        />}
      </section>
    )
  }

  return (
    <section className={bulkPrintMode ? 'bulk-print-mode work-order-list-page' : 'work-order-list-page'}>
      <div className="page-head no-print"><div><h1>Munkalapok</h1><p className="muted">Szerveroldali lapozás, rendezés, megosztható szűrések és személyes mentett nézetek.</p></div><div className="inline-actions"><button className="secondary" onClick={downloadCsv}>CSV export</button><button onClick={() => navigate('/work-orders/new')}>+ Új munkalap</button></div></div>
      <nav className="work-order-subnav no-print" aria-label="Munkalap aloldalak"><NavLink to="/service/work-orders" end>Munkalapok</NavLink><NavLink to="/service/work-orders/archives">Archívum</NavLink></nav>
      {feedback}
      {bulkCreatedCount > 0 && <div className="success no-print">{bulkCreatedCount} karbantartási munkalap létrejött és kijelölésre került.{bulkSkippedCount > 0 ? ` ${bulkSkippedCount} eszköz kimaradt, mert már volt nyitott karbantartási munkalapja.` : ''} A kijelölteket egy gombbal nyomtathatod.</div>}

      <div className="panel work-order-list-controls no-print">
        <div className="work-order-list-primary-controls">
          <div className="debounced-search-wrap">
            <input placeholder="Keresés munkalapszám, feladat, ügyfél, helyszín, technikus vagy eszköz szerint..." value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
            {searchPending && <span className="search-pending">Keresés...</span>}
          </div>
          <select aria-label="Mentett nézet betöltése" defaultValue="" onChange={(event) => { const view = savedViews.find((item) => item.id === Number(event.target.value)); if (view) applySavedView(view); event.target.value = '' }}>
            <option value="">Mentett nézet betöltése...</option>
            {savedViews.map((view) => <option key={view.id} value={view.id}>{view.is_default ? '★ ' : ''}{view.name}</option>)}
          </select>
          <button type="button" className="secondary" onClick={() => setSavedViewDialogOpen(true)}>Nézet mentése</button>
          <details className="column-picker">
            <summary>Oszlopok ({visibleColumns.length})</summary>
            <div className="column-picker-popover">
              {workOrderColumnOptions.map(([key, label]) => <label key={key}><input type="checkbox" checked={visibleColumns.includes(key)} disabled={key === 'number'} onChange={(event) => toggleVisibleColumn(key, event.target.checked)} /> {label}</label>)}
            </div>
          </details>
          {(activeListFilterCount > 0 || searchParams.has('columns') || searchParams.has('sort') || searchParams.has('page_size')) && <button type="button" className="ghost-button" onClick={resetListView}>Alaphelyzet</button>}
        </div>

        <div className="filters work-order-filters round-three">
          <select value={filters.status} onChange={(event) => updateListParam('status', event.target.value)}><option value="">Összes státusz</option>{statuses.map((status) => <option key={status}>{status}</option>)}</select>
          <select value={filters.open_state} onChange={(event) => updateListParam('open_state', event.target.value)}><option value="">Nyitott és lezárt</option><option value="open">Csak nyitott</option><option value="closed">Csak lezárt</option><option value="cancelled">Csak sztornózott</option></select>
          <select value={filters.priority} onChange={(event) => updateListParam('priority', event.target.value)}><option value="">Összes prioritás</option>{priorities.map((priority) => <option key={priority}>{priority}</option>)}</select>
          <select value={filters.work_type} onChange={(event) => updateListParam('work_type', event.target.value)}><option value="">Összes munkatípus</option>{workTypes.map((type) => <option key={type} value={type}>{workTypeLabel(type)}</option>)}</select>
          <select value={filters.company_code} onChange={(event) => updateListParam('company_code', event.target.value)}><option value="">Összes cégkód</option>{companyCodes.map((code) => <option key={code}>{code}</option>)}</select>
          <select value={filters.customer_id} onChange={(event) => handleFilterCustomerChange(event.target.value)}><option value="">Összes ügyfél</option>{customers.map((customer) => <option value={customer.id} key={customer.id}>{customer.company_code ? `${customer.company_code} · ` : ''}{customer.name}</option>)}</select>
          <select value={filters.technician_id} onChange={(event) => updateListParam('technician_id', event.target.value)}><option value="">Összes technikus</option>{technicians.map((technician) => <option value={technician.id} key={technician.id}>{technician.full_name}</option>)}</select>
          <select value={filters.asset_id} onChange={(event) => updateListParam('asset_id', event.target.value)}><option value="">Összes eszköz</option>{filterAssetOptions.map((asset) => <option value={asset.id} key={asset.id}>{assetLabel(asset)}</option>)}</select>
          <label className="compact-date-filter"><span>Tervezett ettől</span><input type="date" value={filters.date_from} onChange={(event) => updateListParam('date_from', event.target.value)} /></label>
          <label className="compact-date-filter"><span>Tervezett eddig</span><input type="date" value={filters.date_to} onChange={(event) => updateListParam('date_to', event.target.value)} /></label>
        </div>

        {savedViews.length > 0 && <div className="saved-view-chips"><span>Mentett nézetek:</span>{savedViews.map((view) => <span className="saved-view-chip" key={view.id}><button type="button" onClick={() => applySavedView(view)}>{view.is_default ? '★ ' : ''}{view.name}</button><button type="button" aria-label={`${view.name} törlése`} onClick={() => deleteSavedView(view)}>×</button></span>)}</div>}
      </div>

      <div className="work-order-list-toolbar no-print">
        <span><strong>{pageData.total}</strong> találat · {pageData.page}. / {pageData.pages}. oldal</span>
        <label>Oldalméret <select value={listPageSize} onChange={(event) => updateListParam('page_size', event.target.value)}>{[25, 50, 100, 200].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      </div>

      <div className="no-print">
        {selectedOrderIds.length > 0 && <div className="bulk-selection-toolbar sticky-selection-toolbar"><div><strong>{selectedOrderIds.length}</strong> munkalap kijelölve</div><div className="inline-actions">{user?.role?.name !== 'Technikus / szerelő' && <button onClick={openBulkEdit}>Szerkesztés</button>}<button onClick={printSelectedOrders}>Nyomtatás</button><button className="secondary" onClick={() => setSelectedOrderIds([])}>Kijelölés törlése</button></div></div>}
        {listLoading && <div className="table-loading">Munkalapok betöltése...</div>}
        {!listLoading && !orders.length && <div className="panel empty-list-state">Nincs a szűrésnek megfelelő munkalap.</div>}
        {orders.length > 0 && <DataTable
          rows={orders}
          onRowClick={select}
          columns={listColumns}
          controlledSort={{ key: listSort, dir: listOrder }}
          onSort={changeListSort}
          selection={{ selectedKeys: selectedOrderIds, onToggle: toggleOrderSelection, onToggleAll: toggleAllOrders }}
          expandable={{ expandedKeys: expandedArchiveOrderIds, onToggle: toggleInlineArchive, render: renderInlineArchive, label: (row, expanded) => expanded ? `${row.number} archívumának összecsukása` : `${row.number} archívumának kibontása` }}
          actions={(row) => <details className="work-order-action-menu"><summary aria-label={`Műveletek: ${row.number}`}>⋮</summary><div className="work-order-action-menu-popover"><button onClick={() => select(row)}>Megnyitás</button>{user?.role?.name !== 'Technikus / szerelő' && <button onClick={() => openEdit(row)}>Szerkesztés</button>}{!['lezárva', 'törölve / sztornózva'].includes(row.status) && <button onClick={() => navigate(`/work-orders/${row.id}/close`)}>Lezárás</button>}<button onClick={() => setInlineArchiveUploadOrder(row)}>Archiválás</button>{user?.role?.name !== 'Technikus / szerelő' && <button className="danger" onClick={() => cancel(row)}>Sztornózás</button>}</div></details>}
        />}
        <WorkOrderPagination current={pageData.page} pages={pageData.pages} onChange={(value) => updateListParam('page', value > 1 ? String(value) : '', false)} />
      </div>

      {inlineArchiveUploadOrder && <WorkOrderArchiveUploadModal
        targetType="workOrder"
        targetId={inlineArchiveUploadOrder.id}
        title={`${inlineArchiveUploadOrder.number} archiválása`}
        defaultSourceNumber={inlineArchiveUploadOrder.number}
        defaultWorkDate={inlineArchiveUploadOrder.completed_at || inlineArchiveUploadOrder.planned_date}
        onClose={() => setInlineArchiveUploadOrder(null)}
        onSaved={() => {
          const orderId = inlineArchiveUploadOrder.id
          setInlineArchiveUploadOrder(null)
          loadInlineArchives(orderId, true)
        }}
      />}

      {savedViewDialogOpen && <div className="modal-backdrop no-print" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !savedViewSaving) setSavedViewDialogOpen(false) }}>
        <form className="modal-card saved-view-modal" onSubmit={saveCurrentView}>
          <div className="modal-head"><div><h2>Aktuális nézet mentése</h2><p>A szűrők, a rendezés, az oldalméret és a látható oszlopok kerülnek mentésre.</p></div><button type="button" className="secondary" onClick={() => setSavedViewDialogOpen(false)}>Bezárás</button></div>
          <Field label="Nézet neve"><input required maxLength="120" value={savedViewName} onChange={(event) => setSavedViewName(event.target.value)} /></Field>
          <label className="bulk-edit-checkbox"><input type="checkbox" checked={savedViewDefault} onChange={(event) => setSavedViewDefault(event.target.checked)} /> Ez legyen az alapértelmezett munkalapnézet</label>
          <div className="inline-actions modal-actions"><button type="button" className="secondary" disabled={savedViewSaving} onClick={() => setSavedViewDialogOpen(false)}>Mégse</button><button type="submit" disabled={savedViewSaving}>{savedViewSaving ? 'Mentés...' : 'Nézet mentése'}</button></div>
        </form>
      </div>}
      {bulkEditOpen && <div className="modal-backdrop no-print" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !bulkEditSubmitting) setBulkEditOpen(false) }}>
        <form className="modal-card bulk-edit-modal" onSubmit={submitBulkEdit}>
          <div className="modal-head"><div><h2>Kijelölt munkalapok szerkesztése</h2><p>{selectedOrderIds.length} munkalapra alkalmazott közös módosítás.</p></div><button type="button" className="secondary" disabled={bulkEditSubmitting} onClick={() => setBulkEditOpen(false)}>Bezárás</button></div>
          <div className="bulk-edit-notice"><strong>Nem módosítható tömegesen:</strong> ügyfél, helyszín, kapcsolattartó és kapcsolódó eszköz. Ezek minden munkalapon változatlanok maradnak.</div>
          <div className="bulk-edit-field"><label className="bulk-edit-checkbox"><input type="checkbox" checked={bulkEditForm.apply_status} onChange={(event) => setBulkEditForm((current) => ({ ...current, apply_status: event.target.checked }))} /> Státusz módosítása minden kijelölt munkalapon</label><select value={bulkEditForm.status} disabled={!bulkEditForm.apply_status} onChange={(event) => setBulkEditForm((current) => ({ ...current, status: event.target.value }))}><option value="__unchanged__">Válassz státuszt</option>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select><small>A kiválasztott státusz minden kijelölt munkalapra érvényes lesz. Lezáráskor a rendszer a hiányzó lezárási időpontokat is rögzíti.</small></div>
          <div className="bulk-edit-field"><label className="bulk-edit-checkbox"><input type="checkbox" checked={bulkEditForm.apply_planned_date} onChange={(event) => setBulkEditForm((current) => ({ ...current, apply_planned_date: event.target.checked }))} /> Tervezett nap módosítása minden kijelölt munkalapon</label><input type="date" value={bulkEditForm.planned_date} disabled={!bulkEditForm.apply_planned_date} required={bulkEditForm.apply_planned_date} onChange={(event) => setBulkEditForm((current) => ({ ...current, planned_date: event.target.value }))} /><small>Ha a munkalapon van tervezett kezdési és befejezési idő, azok órája megmarad, csak a dátum kerül át az új napra.</small></div>
          <div className="bulk-edit-field"><label className="bulk-edit-checkbox"><input type="checkbox" checked={bulkEditForm.apply_technician} onChange={(event) => setBulkEditForm((current) => ({ ...current, apply_technician: event.target.checked }))} /> Elsődleges technikus módosítása minden kijelölt munkalapon</label><select value={bulkEditForm.technician_id} disabled={!bulkEditForm.apply_technician} onChange={(event) => setBulkEditForm((current) => ({ ...current, technician_id: event.target.value }))}><option value="__unchanged__">Válassz technikust</option><option value="__none__">Nincs kijelölve</option>{technicians.map((technician) => <option key={technician.id} value={technician.id}>{technician.full_name}</option>)}</select></div>
          <div className="bulk-edit-field"><label className="bulk-edit-checkbox"><input type="checkbox" checked={bulkEditForm.apply_secondary_technician} onChange={(event) => setBulkEditForm((current) => ({ ...current, apply_secondary_technician: event.target.checked }))} /> Második technikus módosítása minden kijelölt munkalapon</label><select value={bulkEditForm.secondary_technician_id} disabled={!bulkEditForm.apply_secondary_technician} onChange={(event) => setBulkEditForm((current) => ({ ...current, secondary_technician_id: event.target.value }))}><option value="__unchanged__">Válassz technikust</option><option value="__none__">Nincs kijelölve</option>{technicians.map((technician) => <option key={technician.id} value={technician.id}>{technician.full_name}</option>)}</select></div>
          <div className="inline-actions modal-actions"><button type="button" className="secondary" disabled={bulkEditSubmitting} onClick={() => setBulkEditOpen(false)}>Mégse</button><button type="submit" disabled={bulkEditSubmitting}>{bulkEditSubmitting ? 'Mentés...' : `Módosítás alkalmazása (${selectedOrderIds.length})`}</button></div>
        </form>
      </div>}
      <div className="bulk-print-container" aria-hidden={!bulkPrintMode}>{bulkPrintOrders.map((order) => <div className="bulk-print-item" key={order.id}><PrintableWorkOrder order={order} /></div>)}</div>
    </section>
  )
}

function WorkOrderDetailPage({ order, user, tab, history, historyLoading, materialsCatalog, onTabChange, onEdit, onClose, onArchive, onPrint, onAssetOpen, archiveRefreshKey }) {
  const tabs = [
    ['overview', 'Áttekintés'],
    ['assets', `Eszközök (${order.assets?.length || 0})`],
    ['materials', `Anyagok (${order.materials?.length || 0})`],
    ['time', 'Idő és munkavégzés'],
    ['archives', 'Archív fájlok'],
    ['history', 'Történet'],
  ]
  const roleName = user?.role?.name
  const canEdit = roleName !== 'Technikus / szerelő'
  const assignedTechnicianIds = order.technician_ids || [order.technician_id, order.secondary_technician_id].filter(Boolean)
  const canClose = !['lezárva', 'törölve / sztornózva'].includes(order.status)
    && (roleName !== 'Technikus / szerelő' || !assignedTechnicianIds.length || assignedTechnicianIds.includes(user?.id))
  const completedStatus = ['kész', 'lezárva'].includes(order.status)
  const summaryTimeLabel = completedStatus ? 'Tényleges munkavégzés' : 'Tervezett idő'
  const summaryTime = completedStatus
    ? formatTimeRange(order.started_at, order.completed_at, null)
    : formatTimeRange(order.planned_start_at, order.planned_end_at, order.planned_date)

  return (
    <div className="work-order-detail-shell no-print">
      <header className="work-order-detail-header">
        <div className="work-order-detail-title">
          <div className="work-order-title-line">
            <h1>{order.number}</h1>
            <span className={`work-order-status-badge status-${statusSlug(order.status)}`}>{order.status}</span>
            <span className={`priority-badge priority-${statusSlug(order.priority)}`}>{order.priority}</span>
          </div>
          <p>{order.customer_name || '-'}{order.location_name ? ` · ${order.location_name}` : ''}</p>
        </div>
        <div className="inline-actions detail-header-actions">
          {canEdit && <button onClick={onEdit}>Szerkesztés</button>}
          {canClose && <button className="success-button" onClick={onClose}>Lezárás</button>}
          <button className="secondary" onClick={onArchive}>Archiválás</button>
          <button className="secondary" onClick={onPrint}>Nyomtatás</button>
        </div>
      </header>

      <div className="work-order-summary-grid">
        <SummaryCard label="Technikus" value={technicianDisplay(order)} />
        <SummaryCard label={summaryTimeLabel} value={summaryTime} />
        <SummaryCard label="Munka típusa" value={workTypeLabel(order.work_type)} />
        <SummaryCard label="Kapcsolódó eszközök" value={`${order.assets?.length || 0} db`} />
        <SummaryCard label="Gép / gyári szám" value={workOrderAssetSummary(order)} />
      </div>

      <nav className="work-order-tabs" aria-label="Munkalap adatlap fülei">
        {tabs.map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => onTabChange(key)}>{label}</button>)}
      </nav>

      {tab === 'overview' && <div className="work-order-tab-content overview-grid">
        <section className="panel detail-section detail-section-wide">
          <h2>Hiba / feladat leírása</h2>
          <p className="prewrap detail-primary-text">{value(order.description)}</p>
        </section>
        <section className="panel detail-section detail-section-wide">
          <h2>Elvégzett munka</h2>
          <p className="prewrap detail-primary-text">{value(order.work_done)}</p>
        </section>
        <section className="panel detail-section">
          <h2>Ügyfél és helyszín</h2>
          <DetailRow label="Ügyfél" value={order.customer_name} />
          <DetailRow label="Cégkód" value={order.customer_company_code} />
          <DetailRow label="Helyszín" value={order.location_name} />
          <DetailRow label="Cím" value={order.location_address || order.customer_address} />
        </section>
        <section className="panel detail-section">
          <h2>Kapcsolattartó</h2>
          <DetailRow label="Név" value={order.customer_contact_person} />
          <DetailRow label="Telefon" value={order.customer_phone} />
          <DetailRow label="E-mail" value={order.customer_email} />
          <DetailRow label="Típus" value={order.contact?.category} />
        </section>
        <section className="panel detail-section detail-section-wide">
          <h2>Kapcsolódó gépek</h2>
          {order.assets?.length ? <div className="work-order-overview-assets">{order.assets.map((asset) => <button type="button" className="work-order-overview-asset" key={asset.id} onClick={() => onAssetOpen(asset.id)}><span>{assetMachineType(asset)}</span><strong>Gyári szám: {asset.serial_number || '-'}</strong></button>)}</div> : <p>Nincs kapcsolódó eszköz.</p>}
        </section>
        <section className="panel detail-section">
          <h2>Munkalap adatai</h2>
          <DetailRow label="Prioritás" value={order.priority} />
          <DetailRow label="Munka típusa" value={workTypeLabel(order.work_type)} />
          <DetailRow label="Szerződés" value={order.contract_number} />
          <DetailRow label="Szerződés típusa" value={order.contract_type} />
          <DetailRow label="Létrehozva" value={formatDate(order.created_at)} />
          <DetailRow label="Utolsó módosítás" value={formatDate(order.updated_at)} />
        </section>
        <section className="panel detail-section">
          <h2>Lezárási adatok</h2>
          <DetailRow label="Végállapot" value={order.final_status} />
          <DetailRow label="Lezárva" value={formatDate(order.closed_at)} />
          <DetailRow label="Munkaidő" value={order.labor_hours === null || order.labor_hours === undefined ? null : `${formatNumber(order.labor_hours)} óra`} />
        </section>
        {order.internal_note && <section className="panel detail-section detail-section-wide"><h2>Belső megjegyzés</h2><p className="prewrap">{order.internal_note}</p></section>}
        <WorkOrderPrinterService order={order} materials={materialsCatalog} meterOnly />
      </div>}

      {tab === 'assets' && <div className="work-order-tab-content">
        <section className="panel detail-section">
          <div className="section-title-row"><div><h2>Kapcsolódó eszközök</h2><p className="muted">Az eszköz megnyitásához kattints a sorára.</p></div></div>
          <div className="compact-table-wrap">
            <table className="compact-detail-table">
              <thead><tr><th>Eszköz</th><th>Gyári szám</th><th>Állapot</th><th>Utolsó karbantartás</th><th>Utolsó számlálók</th></tr></thead>
              <tbody>{order.assets?.length ? order.assets.map((asset) => <tr key={asset.id} className="clickable-row" tabIndex="0" onClick={() => onAssetOpen(asset.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onAssetOpen(asset.id) }}><td><strong>{asset.display_name}</strong><small>{asset.company_code || '-'}</small></td><td>{value(asset.serial_number)}</td><td><span className={`asset-status status-${statusSlug(asset.status)}`}>{value(asset.status)}</span></td><td>{formatDateOnly(asset.last_maintenance_date)}</td><td>{formatAssetMeter(asset)}</td></tr>) : <tr><td colSpan="5">Nincs kapcsolódó eszköz.</td></tr>}</tbody>
            </table>
          </div>
        </section>
        <WorkOrderPrinterService order={order} materials={materialsCatalog} />
      </div>}

      {tab === 'materials' && <div className="work-order-tab-content">
        <section className="panel detail-section">
          <h2>Felhasznált anyagok</h2>
          <div className="compact-table-wrap">
            <table className="compact-detail-table">
              <thead><tr><th>Cikkszám</th><th>Megnevezés</th><th>Mennyiség</th><th>Egységár</th><th>Nettó érték</th><th>Megjegyzés</th></tr></thead>
              <tbody>
                {order.materials?.length ? order.materials.map((line) => <tr key={line.id}><td>{value(line.sku)}</td><td>{value(line.name)}</td><td>{formatNumber(line.quantity)} {line.unit || ''}</td><td>{formatMoney(line.unit_price)}</td><td>{formatMoney(netValue(line))}</td><td>{value(line.note)}</td></tr>) : <tr><td colSpan="6">Nincs rögzített anyagfelhasználás.</td></tr>}
              </tbody>
              {order.materials?.length > 0 && <tfoot><tr><th colSpan="4">Összesen</th><th>{formatMoney(order.materials.reduce((sum, line) => sum + netValue(line), 0))}</th><th></th></tr></tfoot>}
            </table>
          </div>
        </section>
      </div>}

      {tab === 'time' && <div className="work-order-tab-content time-detail-grid">
        <section className="panel detail-section">
          <h2>Tervezett idő</h2>
          <DetailRow label="Tervezett nap" value={formatDateOnly(order.planned_date)} />
          <DetailRow label="Kezdés" value={formatDate(order.planned_start_at)} />
          <DetailRow label="Befejezés" value={formatDate(order.planned_end_at)} />
          <DetailRow label="Tervezett időtartam" value={formatDuration(order.planned_start_at, order.planned_end_at)} />
        </section>
        <section className="panel detail-section">
          <h2>Tényleges munkavégzés</h2>
          <DetailRow label="Kezdés" value={formatDate(order.started_at)} />
          <DetailRow label="Befejezés" value={formatDate(order.completed_at)} />
          <DetailRow label="Mért időtartam" value={formatDuration(order.started_at, order.completed_at)} />
          <DetailRow label="Rögzített munkaidő" value={order.labor_hours === null || order.labor_hours === undefined ? null : `${formatNumber(order.labor_hours)} óra`} />
        </section>
        <section className="panel detail-section">
          <h2>Felelősség és állapot</h2>
          <DetailRow label="Technikus" value={technicianDisplay(order)} />
          <DetailRow label="Státusz" value={order.status} />
          <DetailRow label="Lezárás időpontja" value={formatDate(order.closed_at)} />
          <DetailRow label="Verzió" value={order.version} />
        </section>
      </div>}

      {tab === 'archives' && <WorkOrderArchivesTab order={order} user={user} refreshKey={archiveRefreshKey} />}

      {tab === 'history' && <div className="work-order-tab-content">
        <section className="panel detail-section">
          <h2>Munkalap története</h2>
          {historyLoading && <div className="table-loading">Történet betöltése...</div>}
          {!historyLoading && !history.length && <p className="muted">Nincs megjeleníthető történeti bejegyzés.</p>}
          {!historyLoading && history.length > 0 && <div className="work-order-timeline">{history.map((entry) => <article key={entry.id}><div className="timeline-dot"></div><div className="timeline-content"><div className="timeline-heading"><strong>{entry.action}</strong><time>{formatDate(entry.created_at)}</time></div><p>{entry.description}</p><small>{entry.user_name || 'Rendszer'}{entry.asset_name ? ` · ${entry.asset_name}` : ''}</small></div></article>)}</div>}
        </section>
      </div>}
    </div>
  )
}


function WorkOrderArchivesTab({ order, user, refreshKey = 0 }) {
  const [archives, setArchives] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    api(`/work-orders/${order.id}/archives`)
      .then((rows) => { if (active) setArchives(rows) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [order.id, refreshKey])

  return <div className="work-order-tab-content">
    <section className="panel detail-section">
      <div className="section-title-row"><div><h2>Archív fájlok</h2><p className="muted">A feltöltés automatikusan kapcsolódik a munkalaphoz és annak jelenlegi eszközeihez.</p></div><button type="button" onClick={() => setUploadOpen(true)}>Fájl archiválása</button></div>
      {error && <div className="error">{error}</div>}
      <WorkOrderArchiveTable archives={archives} loading={loading} emptyText="Ehhez a munkalaphoz még nincs archív fájl." user={user} onDeleted={(deleted) => setArchives((rows) => rows.filter((row) => row.id !== deleted.id))} />
    </section>
    {uploadOpen && <WorkOrderArchiveUploadModal
      targetType="workOrder"
      targetId={order.id}
      title={`${order.number} archiválása`}
      defaultSourceNumber={order.number}
      defaultWorkDate={order.completed_at || order.planned_date}
      onClose={() => setUploadOpen(false)}
      onSaved={(created) => { setArchives((rows) => [created, ...rows]); setUploadOpen(false) }}
    />}
  </div>
}

function WorkOrderClosePage({ order, technicians, form, setForm, onSubmit, onCancel, onArchiveUpload }) {
  return (
    <div className="work-order-close-shell">
      <header className="panel close-page-header">
        <div><span className="eyebrow">Munkalap lezárása</span><h1>{order.number}</h1><p>{order.customer_name}{order.location_name ? ` · ${order.location_name}` : ''}</p></div>
        <div className="close-page-summary"><span>Munka típusa<strong>{workTypeLabel(order.work_type)}</strong></span><span>Kapcsolt eszköz<strong>{order.assets?.length || 0} db</strong></span></div>
      </header>
      <form className="panel work-order-close-form" onSubmit={onSubmit}>
        <div className="close-form-intro"><h2>Elvégzett munka és lezárási adatok</h2><p className="muted">A lezárás után a munkalap státusza lezártra vált. Karbantartás esetén a kapcsolt eszközök utolsó karbantartási dátuma is frissül.</p></div>
        <div className="close-archive-upload"><div><h3>Beszkennelt munkalap</h3><p className="muted">A lezárás előtt feltöltheted az aláírt vagy beszkennelt példányt. A fájl azonnal a munkalaphoz és annak eszközeihez kapcsolódik.</p></div><button type="button" className="secondary" onClick={onArchiveUpload}>Archív fájl feltöltése</button></div>
        <Field label="Elvégzett munka"><textarea required rows="8" value={form.work_done} onChange={(event) => setForm((current) => ({ ...current, work_done: event.target.value }))} /></Field>
        <Field label="Végállapot"><textarea required rows="4" value={form.final_status} onChange={(event) => setForm((current) => ({ ...current, final_status: event.target.value }))} /></Field>
        <div className="close-time-grid">
          <Field label="Tényleges kezdés"><input type="datetime-local" required value={form.started_at} onChange={(event) => setForm((current) => ({ ...current, started_at: event.target.value }))} /></Field>
          <Field label="Tényleges befejezés"><input type="datetime-local" required min={form.started_at || undefined} value={form.completed_at} onChange={(event) => setForm((current) => ({ ...current, completed_at: event.target.value }))} /></Field>
          <Field label="Munkaidő (óra)"><input type="number" required min="0" step="0.25" value={form.labor_hours} onChange={(event) => setForm((current) => ({ ...current, labor_hours: event.target.value }))} /></Field>
          <Field label="Elsődleges technikus"><select required value={form.technician_id} onChange={(event) => setForm((current) => ({ ...current, technician_id: event.target.value }))}><option value="">Válassz technikust</option>{technicians.map((technician) => <option key={technician.id} value={technician.id} disabled={String(technician.id) === String(form.secondary_technician_id)}>{technician.full_name}</option>)}</select></Field>
          <Field label="Második technikus"><select value={form.secondary_technician_id} onChange={(event) => setForm((current) => ({ ...current, secondary_technician_id: event.target.value }))}><option value="">Nincs kijelölve</option>{technicians.map((technician) => <option key={technician.id} value={technician.id} disabled={String(technician.id) === String(form.technician_id)}>{technician.full_name}</option>)}</select></Field>
        </div>
        <div className="sticky-form-actions"><button type="button" className="secondary" onClick={onCancel}>Mégse</button><button type="submit" className="success-button">Munkalap lezárása</button></div>
      </form>
    </div>
  )
}

function WorkOrderAssetListCell({ assets: linkedAssets = [] }) {
  if (!linkedAssets.length) return <span className="muted">Nincs kapcsolt eszköz</span>
  return <div className="work-order-assets-cell">{linkedAssets.map((asset) => <div key={asset.id}><strong>{assetMachineType(asset)}</strong><small>Gyári szám: {asset.serial_number || '-'}</small></div>)}</div>
}

function SummaryCard({ label, value: cardValue }) {
  return <div className="work-order-summary-card"><span>{label}</span><strong>{value(cardValue)}</strong></div>
}

function DetailRow({ label, value: rowValue }) {
  return <div className="detail-row"><span>{label}</span><strong>{value(rowValue)}</strong></div>
}

function PrintableWorkOrder({ order, onPrint = null, onEdit = null, closeBox = null }) {
  const supplier = order.supplier || {}
  const customerAddress = order.location_address || order.customer_address || ''
  const materials = order.materials || []
  const assets = order.assets || []
  const materialNetTotal = materials.reduce((sum, line) => sum + netValue(line), 0)

  return (
    <div className="print-sheet panel worksheet-print">
      <div className="page-head no-print"><h2>Munkalap: {order.number}</h2><div className="inline-actions">{onEdit && <button onClick={onEdit}>Szerkesztés</button>}{onPrint && <button onClick={onPrint}>Nyomtatás</button>}</div></div>
      <div className="worksheet-title"><h1>MUNKALAP</h1><div className="worksheet-number">{printValue(order.number)}</div></div>

      <div className="worksheet-parties">
        <section>
          <h3>Szállító / szolgáltató</h3>
          <p className="party-name">{printValue(supplier.display_name || supplier.short_name || supplier.legal_name)}</p>
          {supplier.legal_name && supplier.legal_name !== (supplier.display_name || supplier.short_name) && <p>{supplier.legal_name}</p>}
          <p><strong>Cím:</strong> {printValue(supplier.address_for_worksheet || supplier.contact_address || supplier.registered_address)}</p>
          <p><strong>Adószám:</strong> {printValue(supplier.tax_number)}</p>
          <p><strong>Cégjegyzékszám:</strong> {printValue(supplier.company_registration_number)}</p>
          <p><strong>Telefon:</strong> {printValue(supplierWorksheetPhone(supplier))}</p>
          <p><strong>E-mail:</strong> {printValue(supplierWorksheetEmail(supplier))}</p>
        </section>
        <section>
          <h3>Vevő / megrendelő</h3>
          <p className="party-name">{printValue(order.customer_name)}</p>
          <p><strong>Cím:</strong> {printValue(customerAddress)}</p>
          <p><strong>Helyszín:</strong> {printValue(order.location_name)}</p>
          <p><strong>Kapcsolattartó:</strong> {printValue(order.customer_contact_person)}</p>
          <p><strong>Telefon:</strong> {printValue(order.customer_phone)}</p>
          <p><strong>E-mail:</strong> {printValue(order.customer_email)}</p>
        </section>
      </div>

      <table className="worksheet-meta">
        <tbody>
          <tr><th>Munkalapszám</th><td>{printValue(order.number)}</td><th>Státusz</th><td>{printValue(order.status)}</td></tr>
          <tr><th>Prioritás</th><td>{printValue(order.priority)}</td><th>Technikusok</th><td>{technicianDisplay(order)}</td></tr>
          <tr><th>Munkaidő</th><td>{order.labor_hours === null || order.labor_hours === undefined ? '' : `${formatNumber(order.labor_hours)} óra`}</td><th>Munka típusa</th><td>{printWorkTypeLabel(order.work_type)}</td></tr>
          <tr><th>Tervezett nap</th><td>{formatPrintDateOnly(order.planned_date)}</td><th>Szerződés típusa</th><td>{printValue(order.contract_type)}</td></tr>
          <tr><th>Tényleges kezdés</th><td colSpan="3">{formatPrintDate(order.started_at)}</td></tr>
          <tr><th>Tényleges befejezés</th><td colSpan="3">{formatPrintDate(order.completed_at)}</td></tr>
        </tbody>
      </table>

      <h3>Kapcsolódó eszközök</h3>
      <table className="worksheet-table">
        <thead><tr><th>Belső azonosító</th><th>Típus / modell</th><th>Gyártó</th><th>Gyári szám</th><th>Utolsó számlálók</th><th>Utolsó karbantartás</th></tr></thead>
        <tbody>
          {assets.length ? assets.map((asset) => <tr key={asset.id}><td>{printValue(visibleInternalId(asset))}</td><td>{printValue(asset.model || asset.type)}</td><td>{printValue(asset.manufacturer)}</td><td>{printValue(asset.serial_number)}</td><td>{formatPrintAssetMeter(asset)}</td><td>{formatPrintDateOnly(asset.last_maintenance_date)}</td></tr>) : <tr><td colSpan="6">Nincs kapcsolt eszköz</td></tr>}
        </tbody>
      </table>

      <h3 className="worksheet-block-label">Hiba / feladat leírása</h3>
      <div className="worksheet-block worksheet-block--double"><p>{printValue(order.description)}</p></div>
      <h3 className="worksheet-block-label">Elvégzett munka</h3>
      <div className="worksheet-block worksheet-block--work-done"><p>{printValue(order.work_done)}</p></div>

      <div className="no-print">
        <h3>Felhasznált anyagok</h3>
        <table className="worksheet-table">
          <thead><tr><th>Cikkszám</th><th>Megnevezés</th><th>Mennyiség</th><th>Egység</th><th>Egységár</th><th>Nettó érték</th><th>Megjegyzés</th></tr></thead>
          <tbody>
            {materials.length ? materials.map((line) => <tr key={line.id}><td>{value(line.sku)}</td><td>{value(line.name)}</td><td>{formatNumber(line.quantity)}</td><td>{value(line.unit)}</td><td>{formatMoney(line.unit_price)}</td><td>{formatMoney(netValue(line))}</td><td>{value(line.note)}</td></tr>) : <tr><td colSpan="7">Nincs rögzített anyagfelhasználás</td></tr>}
            <tr className="worksheet-total"><td colSpan="5">Anyag nettó összesen</td><td>{materials.length ? formatMoney(materialNetTotal) : '-'}</td><td></td></tr>
          </tbody>
        </table>
      </div>
      <h3 className="worksheet-block-label">Végállapot</h3>
      <div className="worksheet-block worksheet-block--final-status"><p>{printValue(order.final_status)}</p></div>
      <div className="worksheet-block no-print"><h3>Belső megjegyzés</h3><p>{value(order.internal_note)}</p></div>

      <div className="worksheet-signatures">
        <div><span>Technikus aláírása</span><strong>{technicianDisplay(order)}</strong></div>
        <div><span>Ügyfél aláírása</span></div>
      </div>
      {closeBox}
    </div>
  )
}

function WorkOrderPagination({ current, pages, onChange }) {
  if (pages <= 1) return null
  const entries = paginationEntries(current, pages)
  return <nav className="asset-pagination work-order-pagination" aria-label="Munkalaplista lapozása">
    <button type="button" className="secondary" disabled={current <= 1} onClick={() => onChange(current - 1)}>Előző</button>
    <div className="pagination-pages">
      {entries.map((entry, index) => entry === '…'
        ? <span key={`ellipsis-${index}`} className="pagination-ellipsis">…</span>
        : <button type="button" key={entry} className={entry === current ? 'active' : ''} aria-current={entry === current ? 'page' : undefined} onClick={() => onChange(entry)}>{entry}</button>)}
    </div>
    <button type="button" className="secondary" disabled={current >= pages} onClick={() => onChange(current + 1)}>Következő</button>
  </nav>
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

function normalizeWorkOrderColumns(value) {
  const allowed = new Set(workOrderColumnOptions.map(([key]) => key))
  const parsed = String(value || '').split(',').map((item) => item.trim()).filter((item) => allowed.has(item))
  const unique = [...new Set(parsed.length ? parsed : defaultWorkOrderColumns)]
  if (!unique.includes('number')) unique.unshift('number')
  return unique
}

function statusSlug(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

function workTypeLabel(value) {
  if (!value) return '-'
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function value(input) {
  return input === null || input === undefined || input === '' ? '-' : input
}

function printValue(input) {
  return input === null || input === undefined || input === '' ? '' : input
}

function printWorkTypeLabel(input) {
  return input ? input.charAt(0).toUpperCase() + input.slice(1) : ''
}

function formatPrintDate(input) {
  return input ? formatDate(input) : ''
}

function formatPrintDateOnly(input) {
  return input ? formatDateOnly(input) : ''
}

function formatDate(input) {
  if (!input) return '-'
  const date = new Date(input)
  if (Number.isNaN(date.getTime())) return String(input)
  return date.toLocaleString('hu-HU', { year: 'numeric', month: '2-digit', day: '2-digit', hour: input.length > 10 ? '2-digit' : undefined, minute: input.length > 10 ? '2-digit' : undefined })
}

function formatDateOnly(input) {
  if (!input) return '-'
  const date = new Date(String(input).length <= 10 ? `${input}T00:00:00` : input)
  if (Number.isNaN(date.getTime())) return String(input)
  return date.toLocaleDateString('hu-HU', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function formatTimeRange(start, end, fallbackDate = null) {
  if (!start && !end) return fallbackDate ? formatDateOnly(fallbackDate) : '-'
  const startText = start ? formatDate(start) : '-'
  if (!end) return startText
  const endDate = new Date(end)
  const startDate = start ? new Date(start) : null
  if (startDate && !Number.isNaN(startDate.getTime()) && !Number.isNaN(endDate.getTime()) && startDate.toDateString() === endDate.toDateString()) {
    return `${formatDateOnly(start)} ${startDate.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' })}–${endDate.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' })}`
  }
  return `${startText} – ${formatDate(end)}`
}

function formatDuration(start, end) {
  if (!start || !end) return '-'
  const milliseconds = new Date(end).getTime() - new Date(start).getTime()
  if (!Number.isFinite(milliseconds) || milliseconds <= 0) return '-'
  const totalMinutes = Math.round(milliseconds / 60000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours ? `${hours} óra ` : ''}${minutes ? `${minutes} perc` : ''}`.trim() || '0 perc'
}

function formatNumber(input) {
  if (input === null || input === undefined || input === '') return '-'
  const number = Number(input)
  if (Number.isNaN(number)) return String(input)
  return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 2 }).format(number)
}

function formatMoney(input) {
  if (input === null || input === undefined || input === '') return '-'
  const number = Number(input)
  if (Number.isNaN(number)) return String(input)
  return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 2 }).format(number) + ' Ft'
}

function netValue(line) {
  const quantity = Number(line.quantity || 0)
  const price = Number(line.unit_price || 0)
  if (Number.isNaN(quantity) || Number.isNaN(price) || line.unit_price === null || line.unit_price === undefined) return 0
  return quantity * price
}


function WorkOrderPrinterService({ order, materials = [], meterOnly = false }) {
  const linkedAssets = order.assets || []
  const [assetId, setAssetId] = useState(linkedAssets[0]?.id ? String(linkedAssets[0].id) : '')
  const [tracking, setTracking] = useState(null)
  const [trackingLoading, setTrackingLoading] = useState(false)
  const [meterValue, setMeterValue] = useState('')
  const [blackWhiteValue, setBlackWhiteValue] = useState('')
  const [colorValue, setColorValue] = useState('')
  const [scanValue, setScanValue] = useState('')
  const [componentId, setComponentId] = useState('')
  const [materialId, setMaterialId] = useState('')
  const [replacementNote, setReplacementNote] = useState('')
  const [serviceError, setServiceError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const firstId = linkedAssets[0]?.id ? String(linkedAssets[0].id) : ''
    setAssetId((current) => linkedAssets.some((asset) => String(asset.id) === current) ? current : firstId)
  }, [order.id, linkedAssets.map((asset) => asset.id).join(',')])

  useEffect(() => {
    if (!assetId) { setTracking(null); return }
    loadTracking(assetId)
  }, [assetId])

  async function loadTracking(id) {
    setServiceError('')
    setTrackingLoading(true)
    try {
      const data = await api(`/assets/${id}/printer-tracking`)
      setTracking(data)
      setMeterValue(data.latest_meter?.value ?? '')
      setBlackWhiteValue(data.latest_meter?.black_white_value ?? '')
      setColorValue(data.latest_meter?.color_value ?? '')
      setScanValue(data.latest_meter?.scan_value ?? '')
      if (!data.components.some((component) => String(component.id) === componentId && component.is_active)) {
        setComponentId(data.components.find((component) => component.is_active)?.id ? String(data.components.find((component) => component.is_active).id) : '')
      }
    } catch (error) { setTracking(null); setServiceError(error.message) }
    finally { setTrackingLoading(false) }
  }

  async function recordMeter(event) {
    event.preventDefault(); setServiceError(''); setMessage('')
    try {
      const data = await api(`/assets/${assetId}/meter-readings`, { method: 'POST', body: { value: Number(meterValue), black_white_value: blackWhiteValue === '' ? null : Number(blackWhiteValue), color_value: colorValue === '' ? null : Number(colorValue), scan_value: scanValue === '' ? null : Number(scanValue), work_order_id: order.id } })
      setTracking(data); setMeterValue(data.latest_meter?.value ?? ''); setBlackWhiteValue(data.latest_meter?.black_white_value ?? ''); setColorValue(data.latest_meter?.color_value ?? ''); setScanValue(data.latest_meter?.scan_value ?? ''); setMessage('A számlálóállás rögzítve.')
    } catch (error) { setServiceError(error.message) }
  }

  async function recordReplacement(event) {
    event.preventDefault(); setServiceError(''); setMessage('')
    try {
      const data = await api(`/assets/${assetId}/component-replacements`, {
        method: 'POST',
        body: {
          asset_component_id: Number(componentId),
          meter_value: Number(meterValue),
          material_id: materialId ? Number(materialId) : null,
          work_order_id: order.id,
          note: replacementNote || null,
        },
      })
      setTracking(data); setMeterValue(data.latest_meter?.value ?? ''); setReplacementNote(''); setMessage('Az alkatrészcsere rögzítve.')
    } catch (error) { setServiceError(error.message) }
  }

  if (!linkedAssets.length) return null
  const activeComponents = (tracking?.components || []).filter((component) => component.is_active)

  return (
    <div className="panel no-print work-order-printer-service">
      <div className="section-title-row"><div><h2>{meterOnly ? 'Számlálóállás rögzítése' : 'Nyomtató számláló és alkatrészcsere'}</h2><p className="muted">A rögzített adat automatikusan ehhez a munkalaphoz és a kiválasztott eszközhöz kapcsolódik.</p></div>{assetId && <button type="button" className="secondary" disabled={trackingLoading} onClick={() => loadTracking(assetId)}>Frissítés</button>}</div>
      {trackingLoading && <div className="table-loading">Számlálóadatok betöltése...</div>}
      {serviceError && <div className="error">{serviceError}</div>}
      {message && <div className="success">{message}</div>}
      <div className="printer-service-toolbar">
        <Field label="Kapcsolt eszköz"><select value={assetId} onChange={(event) => setAssetId(event.target.value)}>{linkedAssets.map((asset) => <option value={asset.id} key={asset.id}>{assetLabel(asset)}</option>)}</select></Field>
        <div className="printer-service-summary"><span>Utolsó számlálók</span><strong>{tracking?.latest_meter ? formatMeterReading(tracking.latest_meter) : 'Nincs adat'}</strong></div>
        <div className="printer-service-summary"><span>Havi átlag</span><strong>{tracking?.average_monthly_usage !== null && tracking?.average_monthly_usage !== undefined ? `${formatNumber(tracking.average_monthly_usage)} oldal/hó` : 'Nincs elég adat'}</strong></div>
      </div>
      <div className={`printer-grid compact-printer-grid ${meterOnly ? 'meter-only-grid' : ''}`}>
        <form className="subpanel stack-form" onSubmit={recordMeter}>
          <h3>Számláló rögzítése</h3>
          <Field label="Összes számláló"><input type="number" min="0" required value={meterValue} onChange={(event) => setMeterValue(event.target.value)} /></Field>
          <Field label="FF számláló"><input type="number" min="0" value={blackWhiteValue} onChange={(event) => setBlackWhiteValue(event.target.value)} /></Field>
          <Field label="Színes számláló"><input type="number" min="0" value={colorValue} onChange={(event) => setColorValue(event.target.value)} /></Field>
          <Field label="Scan számláló"><input type="number" min="0" value={scanValue} onChange={(event) => setScanValue(event.target.value)} /></Field>
          <button>Számláló mentése</button>
        </form>
        {!meterOnly && <form className="subpanel stack-form" onSubmit={recordReplacement}>
          <h3>Alkatrészcsere</h3>
          <Field label="Alkatrész"><select required value={componentId} onChange={(event) => setComponentId(event.target.value)}><option value="">Válassz</option>{activeComponents.map((component) => <option value={component.id} key={component.id}>{component.name}{component.part_number ? ` (${component.part_number})` : ''}</option>)}</select></Field>
          <Field label="Felhasznált anyag"><select value={materialId} onChange={(event) => setMaterialId(event.target.value)}><option value="">Nincs megadva</option>{materials.map((material) => <option value={material.id} key={material.id}>{material.sku} – {material.name}</option>)}</select></Field>
          <Field label="Megjegyzés"><input value={replacementNote} onChange={(event) => setReplacementNote(event.target.value)} /></Field>
          <button disabled={!activeComponents.length || meterValue === ''}>Csere rögzítése</button>
          {!activeComponents.length && <small className="muted">Előbb az Eszközök oldalon adj hozzá követett alkatrészt.</small>}
        </form>}
      </div>
    </div>
  )
}

function technicianDisplay(order) {
  const names = order?.technician_names?.length ? order.technician_names : [order?.technician_name, order?.secondary_technician_name].filter(Boolean)
  return names.length ? names.join(', ') : 'Nincs kijelölve'
}

function formatMeterReading(reading) {
  const parts = [`Összes: ${formatIntegerValue(reading.value)}`]
  if (reading.black_white_value !== null && reading.black_white_value !== undefined) parts.push(`FF: ${formatIntegerValue(reading.black_white_value)}`)
  if (reading.color_value !== null && reading.color_value !== undefined) parts.push(`Színes: ${formatIntegerValue(reading.color_value)}`)
  if (reading.scan_value !== null && reading.scan_value !== undefined) parts.push(`Scan: ${formatIntegerValue(reading.scan_value)}`)
  return parts.join(' · ')
}

function formatAssetMeter(asset) {
  if (asset.latest_meter_value === null || asset.latest_meter_value === undefined) return '-'
  const reading = { value: asset.latest_meter_value, black_white_value: asset.latest_meter_black_white_value, color_value: asset.latest_meter_color_value, scan_value: asset.latest_meter_scan_value }
  const date = asset.latest_meter_at ? formatDateOnly(asset.latest_meter_at) : '-'
  return `${formatMeterReading(reading)} · ${date}`
}

function formatPrintAssetMeter(asset) {
  if (asset.latest_meter_value === null || asset.latest_meter_value === undefined) return ''
  const reading = { value: asset.latest_meter_value, black_white_value: asset.latest_meter_black_white_value, color_value: asset.latest_meter_color_value, scan_value: asset.latest_meter_scan_value }
  const date = asset.latest_meter_at ? formatDateOnly(asset.latest_meter_at) : ''
  return [formatMeterReading(reading), date].filter(Boolean).join(' · ')
}

function formatIntegerValue(input) {
  if (input === null || input === undefined || input === '') return '-'
  return new Intl.NumberFormat('hu-HU', { maximumFractionDigits: 0 }).format(Number(input))
}
