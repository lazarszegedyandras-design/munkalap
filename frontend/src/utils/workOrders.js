export function assetMachineType(asset) {
  if (!asset) return 'Ismeretlen gép'
  return [asset.manufacturer, asset.model || asset.type].filter(Boolean).join(' / ') || asset.display_name || 'Ismeretlen gép'
}

export function assetMachineLabel(asset) {
  const machineType = assetMachineType(asset)
  return asset?.serial_number ? `${machineType} · gyári szám: ${asset.serial_number}` : machineType
}

export function workOrderAssetSummary(order) {
  const assets = order?.assets || []
  if (!assets.length) return 'Nincs kapcsolt eszköz'
  return assets.map(assetMachineLabel).join('; ')
}

export function supplierWorksheetPhone(supplier) {
  if (!supplier) return ''
  return supplier.phone_for_worksheet || supplier.worksheet_phone || supplier.phone || supplier.mobile_phone || ''
}

export function supplierWorksheetEmail(supplier) {
  if (!supplier) return ''
  return supplier.email_for_worksheet || supplier.worksheet_email || supplier.email || ''
}
