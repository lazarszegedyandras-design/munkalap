export function formatDateTime(value) {
  if (!value) return '–'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('hu-HU', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
export function formatTime(value) {
  if (!value) return '–'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('hu-HU', { hour: '2-digit', minute: '2-digit' }).format(date)
}
export const PHOTO_LABELS = { before: 'Előtte', after: 'Utána', damage: 'Sérülés', meter: 'Számláló', other: 'Egyéb' }
export function canEditWorkOrder(status) { return !['kész', 'lezárva', 'törölve / sztornózva'].includes(status) }
