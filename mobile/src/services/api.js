import { API_BASE, clearLocalSession, getAccessToken, refreshAccessToken } from './auth.js'

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function parseError(response) {
  const data = await response.clone().json().catch(() => null)
  return new ApiError(data?.detail || `HTTP ${response.status}`, response.status, data)
}

export async function apiFetch(path, options = {}, retry = true) {
  const headers = new Headers(options.headers || {})
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  headers.set('Accept', headers.get('Accept') || 'application/json')
  if (options.body && !(options.body instanceof FormData) && typeof options.body !== 'string') {
    headers.set('Content-Type', 'application/json')
    options = { ...options, body: JSON.stringify(options.body) }
  }
  let response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (response.status === 401 && retry) {
    try {
      const refreshed = await refreshAccessToken()
      if (refreshed) return apiFetch(path, options, false)
    } catch { /* handled below */ }
    await clearLocalSession()
  }
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return null
  return response.json()
}

export async function apiBlob(path) {
  const headers = new Headers()
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response = await fetch(`${API_BASE}${path}`, { headers })
  if (response.status === 401) {
    const refreshed = await refreshAccessToken().catch(() => null)
    if (refreshed) {
      headers.set('Authorization', `Bearer ${refreshed}`)
      response = await fetch(`${API_BASE}${path}`, { headers })
    }
  }
  if (!response.ok) throw await parseError(response)
  return response.blob()
}
