export function workOrderIdFromData(data = {}) {
  if (String(data.source_type || '') !== 'work_order') return null
  const value = Number(data.source_id)
  return Number.isInteger(value) && value > 0 ? value : null
}
