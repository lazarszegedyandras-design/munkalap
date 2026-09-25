import { Capacitor } from '@capacitor/core'
import { PushNotifications } from '@capacitor/push-notifications'
import { apiFetch } from './api.js'
import { workOrderIdFromData } from './pushData.js'

const CHANNEL_ID = import.meta.env.VITE_PUSH_CHANNEL_ID || 'work_orders'
let initialized = false
let listeners = []
let openHandler = null
let foregroundHandler = null

async function handleAction(data) {
  const id = workOrderIdFromData(data)
  if (id && openHandler) await openHandler(id)
}

export async function initializePushNotifications({ onOpenWorkOrder, onForeground } = {}) {
  if (!Capacitor.isNativePlatform()) return { supported: false, granted: false }
  openHandler = onOpenWorkOrder || openHandler
  foregroundHandler = onForeground || foregroundHandler
  if (initialized) return { supported: true, granted: true }
  initialized = true

  const current = await PushNotifications.checkPermissions()
  let permission = current.receive
  if (permission === 'prompt' || permission === 'prompt-with-rationale') {
    permission = (await PushNotifications.requestPermissions()).receive
  }
  if (permission !== 'granted') {
    initialized = false
    return { supported: true, granted: false }
  }

  await PushNotifications.createChannel({
    id: CHANNEL_ID,
    name: 'Munkalap értesítések',
    description: 'Új vagy módosított technikusi munkalapok',
    importance: 5,
    visibility: 1,
    vibration: true,
  }).catch(() => null)

  listeners.push(await PushNotifications.addListener('registration', async token => {
    try {
      await apiFetch('/devices/push-token', { method: 'PUT', body: { token: token.value, enabled: true } })
    } catch (error) {
      console.warn('Push token registration failed', error)
    }
  }))
  listeners.push(await PushNotifications.addListener('registrationError', error => {
    console.warn('Push registration error', error)
  }))
  listeners.push(await PushNotifications.addListener('pushNotificationReceived', notification => {
    foregroundHandler?.(notification)
  }))
  listeners.push(await PushNotifications.addListener('pushNotificationActionPerformed', action => {
    handleAction(action?.notification?.data || {}).catch(error => console.warn('Push deep link failed', error))
  }))

  await PushNotifications.register()
  return { supported: true, granted: true }
}

export async function disablePushNotifications() {
  if (!Capacitor.isNativePlatform()) return
  try { await apiFetch('/devices/push-token', { method: 'DELETE' }) } catch { /* best effort */ }
  try { await PushNotifications.unregister() } catch { /* plugin/device dependent */ }
  for (const listener of listeners) {
    try { await listener.remove() } catch { /* best effort */ }
  }
  listeners = []
  initialized = false
  openHandler = null
  foregroundHandler = null
}
