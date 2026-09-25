import { Capacitor } from '@capacitor/core'
import { SecureStorage } from '@aparajita/capacitor-secure-storage'
import { getDeviceInfo } from './device.js'

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const REFRESH_KEY = 'refresh_token'
let accessToken = null
let previewRefreshToken = null
let refreshPromise = null
let initialized = false

function requireApiBase() {
  if (!API_BASE || !API_BASE.startsWith('https://')) {
    if (!import.meta.env.DEV) throw new Error('A mobil API csak HTTPS címmel használható productionben.')
  }
}

async function initStorage() {
  if (initialized) return
  initialized = true
  if (Capacitor.isNativePlatform()) await SecureStorage.setKeyPrefix('munkalap_mobile_')
}

async function readRefreshToken() {
  await initStorage()
  if (!Capacitor.isNativePlatform()) return previewRefreshToken
  return (await SecureStorage.get(REFRESH_KEY)) || null
}

async function writeRefreshToken(value) {
  await initStorage()
  if (!Capacitor.isNativePlatform()) {
    previewRefreshToken = value || null
    return
  }
  if (value) await SecureStorage.set(REFRESH_KEY, value)
  else await SecureStorage.remove(REFRESH_KEY)
}

function applyAuth(result) {
  accessToken = result?.access_token || null
  if (result?.refresh_token) return writeRefreshToken(result.refresh_token)
  return Promise.resolve()
}

async function authPost(path, body) {
  requireApiBase()
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`)
  return data
}

export async function login(email, password) {
  const device = await getDeviceInfo()
  const result = await authPost('/auth/login', { email, password, ...device })
  if (result?.access_token) await applyAuth(result)
  return result
}

export async function verifyMfa(challengeToken, code) {
  const device = await getDeviceInfo()
  const result = await authPost('/auth/mfa/verify', { challenge_token: challengeToken, code, ...device })
  await applyAuth(result)
  return result
}

export async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const refreshToken = await readRefreshToken()
    if (!refreshToken) return null
    try {
      const result = await authPost('/auth/refresh', { refresh_token: refreshToken })
      await applyAuth(result)
      return accessToken
    } catch (error) {
      accessToken = null
      await writeRefreshToken(null)
      throw error
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

export async function restoreSession() {
  try { return Boolean(await refreshAccessToken()) } catch { return false }
}

export function getAccessToken() { return accessToken }

export async function logout() {
  const token = accessToken
  accessToken = null
  await writeRefreshToken(null)
  if (token && API_BASE) {
    try {
      await fetch(`${API_BASE}/auth/logout`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    } catch { /* best effort */ }
  }
}

export async function clearLocalSession() {
  accessToken = null
  await writeRefreshToken(null)
}
