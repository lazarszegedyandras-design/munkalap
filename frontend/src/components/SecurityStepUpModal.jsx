import React, { useCallback, useRef, useState } from 'react'
import { api } from '../api.js'

function needsStepUp(error) {
  const code = error?.payload?.detail?.code
  return error?.status === 403 && (code === 'recent_mfa_required' || code === 'mfa_setup_required')
}

export default function SecurityStepUpModal({ open, code, error, busy, onCodeChange, onSubmit, onCancel }) {
  if (!open) return null
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card security-step-up" role="dialog" aria-modal="true" aria-labelledby="security-step-up-title">
        <h2 id="security-step-up-title">Biztonsági megerősítés</h2>
        <p className="muted">Add meg a hitelesítő alkalmazás aktuális kódját vagy egy helyreállítási kódot.</p>
        {error && <div className="error">{error}</div>}
        <form onSubmit={onSubmit}>
          <label>MFA-kód
            <input
              autoFocus
              autoComplete="one-time-code"
              inputMode="numeric"
              value={code}
              onChange={(event) => onCodeChange(event.target.value)}
              minLength={6}
              maxLength={32}
              required
            />
          </label>
          <div className="form-actions">
            <button disabled={busy || code.length < 6}>{busy ? 'Ellenőrzés…' : 'Megerősítés'}</button>
            <button type="button" className="secondary" onClick={onCancel} disabled={busy}>Mégse</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function useSecurityStepUp() {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pendingRef = useRef(null)

  const runSensitive = useCallback(async (action) => {
    try {
      return await action()
    } catch (err) {
      if (!needsStepUp(err)) throw err
      if (err?.payload?.detail?.code === 'mfa_setup_required') throw err
      return new Promise((resolve, reject) => {
        pendingRef.current = { action, resolve, reject }
        setCode('')
        setError('')
        setOpen(true)
      })
    }
  }, [])

  const cancel = useCallback(() => {
    const pending = pendingRef.current
    pendingRef.current = null
    setOpen(false)
    setCode('')
    if (pending) pending.reject(new Error('Az MFA megerősítés megszakítva.'))
  }, [])

  async function submit(event) {
    event.preventDefault()
    if (!pendingRef.current || busy) return
    setBusy(true)
    setError('')
    try {
      await api('/auth/mfa/step-up', { method: 'POST', body: { code } })
      const pending = pendingRef.current
      pendingRef.current = null
      setOpen(false)
      setCode('')
      // Exactly one retry: a second recent_mfa_required response is returned to
      // the caller and never reopens the modal automatically.
      try {
        pending.resolve(await pending.action())
      } catch (retryError) {
        pending.reject(retryError)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const modal = (
    <SecurityStepUpModal
      open={open}
      code={code}
      error={error}
      busy={busy}
      onCodeChange={setCode}
      onSubmit={submit}
      onCancel={cancel}
    />
  )

  return { runSensitive, stepUpModal: modal }
}
