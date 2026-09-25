import { Capacitor } from '@capacitor/core'
import { Directory, Filesystem } from '@capacitor/filesystem'
import { Share } from '@capacitor/share'

function safeName(value) {
  return value.replace(/[^A-Za-z0-9._-]/g, '-')
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = reject
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.readAsDataURL(blob)
  })
}

export async function openOrSharePdf(blob, filename) {
  if (!Capacitor.isNativePlatform()) {
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener,noreferrer')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
    return
  }
  const path = safeName(filename || `munkalap-${Date.now()}.pdf`)
  const data = await blobToBase64(blob)
  const result = await Filesystem.writeFile({ path, data, directory: Directory.Cache, recursive: true })
  await Share.share({ title: 'Aláírt munkalap', files: [result.uri], dialogTitle: 'Aláírt munkalap megnyitása / megosztása' })
}
