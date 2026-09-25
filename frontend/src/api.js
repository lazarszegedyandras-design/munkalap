const API_URL = import.meta.env.VITE_API_URL || '/api'

export class ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

// v0.24: the web client no longer persists bearer tokens in localStorage.
// These compatibility helpers intentionally only remove legacy v0.23 tokens.
export function getToken() {
  return null
}

export function setToken(_token) {
  localStorage.removeItem('token')
}

function cookieValue(name) {
  const prefix = `${encodeURIComponent(name)}=`
  const part = document.cookie.split(';').map((item) => item.trim()).find((item) => item.startsWith(prefix))
  return part ? decodeURIComponent(part.slice(prefix.length)) : ''
}

export function csrfHeaders() {
  const token = cookieValue('workapp_csrf')
  return token ? { 'X-CSRF-Token': token } : {}
}

export async function login(email, password) {
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  if (!response.ok) {
    const error = await readError(response)
    throw new ApiError(error.message, response.status, error.payload)
  }
  return response.json()
}

export async function mfaSetup(challengeToken) {
  return apiPublic('/auth/mfa/setup', { method: 'POST', body: { challenge_token: challengeToken } })
}

export async function mfaConfirm(challengeToken, code) {
  return apiPublic('/auth/mfa/confirm', { method: 'POST', body: { challenge_token: challengeToken, code } })
}

export async function mfaVerify(challengeToken, code) {
  return apiPublic('/auth/mfa/verify', { method: 'POST', body: { challenge_token: challengeToken, code } })
}

async function apiPublic(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers,
    body: options.body && !(options.body instanceof FormData) ? JSON.stringify(options.body) : options.body,
  })
  if (!response.ok) {
    const error = await readError(response)
    throw new ApiError(error.message, response.status, error.payload)
  }
  if (response.status === 204) return null
  return response.json()
}

export async function logoutRequest() {
  const response = await fetch(`${API_URL}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
  })
  if (!response.ok && response.status !== 401) {
    const error = await readError(response)
    throw new ApiError(error.message, response.status, error.payload)
  }
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const method = (options.method || 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) Object.assign(headers, csrfHeaders())
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers,
    body: options.body && !(options.body instanceof FormData) ? JSON.stringify(options.body) : options.body,
  })
  if (response.status === 204) return null
  if (!response.ok) {
    const error = await readError(response)
    if (response.status === 401) window.dispatchEvent(new CustomEvent('app:session-expired'))
    if (response.status === 403 && error.payload?.detail?.code === 'permission_required') {
      window.dispatchEvent(new CustomEvent('app:permissions-changed'))
    }
    throw new ApiError(error.message, response.status, error.payload)
  }
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return response.json()
  return response
}

async function readError(response) {
  try {
    const data = await response.json()
    if (Array.isArray(data.detail)) {
      return { message: data.detail.map((item) => item.msg).join(', '), payload: data }
    }
    if (data.detail && typeof data.detail === 'object') {
      return {
        message: data.detail.message || data.detail.detail || JSON.stringify(data.detail),
        payload: data,
      }
    }
    return { message: data.detail || response.statusText, payload: data }
  } catch {
    return { message: response.statusText, payload: null }
  }
}

export const exportUrl = (path) => `${API_URL}${path}`

export async function downloadFile(path, fallbackName = 'export.csv') {
  const response = await fetch(`${API_URL}${path}`, { credentials: 'include' })
  if (!response.ok) {
    const error = await readError(response)
    throw new ApiError(error.message, response.status, error.payload)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/i)
  const name = match?.[1] || fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
