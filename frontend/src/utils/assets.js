const IMPORT_ID_PATTERN = /^IMP-\d{8}-\d+$/i

export function visibleInternalId(asset) {
  const explicit = asset?.display_internal_id
  if (explicit) return explicit
  const raw = asset?.internal_id
  if (!raw || IMPORT_ID_PATTERN.test(String(raw).trim())) return ''
  return raw
}

export function assetLabel(asset) {
  if (!asset) return 'Eszköz'
  if (asset.display_name) return asset.display_name
  const product = [asset.manufacturer, asset.model || asset.type].filter(Boolean).join(' / ')
  if (product && asset.serial_number) return `${product} · gyári szám: ${asset.serial_number}`
  if (asset.serial_number) return `Gyári szám: ${asset.serial_number}`
  if (product) return product
  return visibleInternalId(asset) || 'Eszköz'
}
