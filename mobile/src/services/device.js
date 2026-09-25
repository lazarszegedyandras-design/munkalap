import { Capacitor } from '@capacitor/core'
import { Preferences } from '@capacitor/preferences'

const DEVICE_KEY = 'munkalap_device_uuid'

function uuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `mobile-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export async function getDeviceInfo() {
  let deviceUuid
  if (Capacitor.isNativePlatform()) {
    const stored = await Preferences.get({ key: DEVICE_KEY })
    deviceUuid = stored.value
    if (!deviceUuid) {
      deviceUuid = uuid()
      await Preferences.set({ key: DEVICE_KEY, value: deviceUuid })
    }
  } else {
    // Böngészős preview-ban nem perzisztálunk azonosítót: ez nem production auth mód.
    deviceUuid = globalThis.__munkalapPreviewDeviceUuid ||= uuid()
  }
  return {
    device_uuid: deviceUuid,
    device_name: Capacitor.isNativePlatform() ? 'Android technikusi eszköz' : 'Böngészős fejlesztői preview',
    platform: Capacitor.getPlatform() || 'android',
    app_version: import.meta.env.VITE_APP_VERSION || '0.31.0',
  }
}
