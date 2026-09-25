import React, { useState } from 'react'
import { api } from '../api.js'

export default function ChangePassword({ forced = false, onChanged, onLogout }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError('')
    setSuccess('')
    if (newPassword !== confirmation) {
      setError('Az új jelszó és a megerősítés nem egyezik.')
      return
    }
    setLoading(true)
    try {
      const updatedUser = await api('/auth/change-password', {
        method: 'POST',
        body: { current_password: currentPassword, new_password: newPassword },
      })
      setCurrentPassword('')
      setNewPassword('')
      setConfirmation('')
      setSuccess('A jelszó módosítása sikeres.')
      onChanged?.(updatedUser)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const form = <form className="login-card password-change-card" onSubmit={submit} autoComplete="off">
    <h1>{forced ? 'Jelszócsere szükséges' : 'Saját jelszó módosítása'}</h1>
    {forced && <p>Az alkalmazás használata előtt állíts be új jelszót. Az első admin belépésnél a jelenlegi jelszó üres.</p>}
    <label>Jelenlegi jelszó<input name="current-password-manual" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} type="password" autoComplete="off" /></label>
    <label>Új jelszó<input name="new-password-manual" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} type="password" autoComplete="new-password" minLength={8} required /></label>
    <label>Új jelszó ismét<input name="new-password-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} type="password" autoComplete="new-password" minLength={8} required /></label>
    <small>Legalább 8 karakter, legalább egy nagybetű és egy speciális karakter szükséges.</small>
    {error && <div className="error">{error}</div>}
    {success && <div className="success">{success}</div>}
    <button disabled={loading}>{loading ? 'Mentés...' : 'Jelszó módosítása'}</button>
    {forced && <button type="button" className="secondary" onClick={onLogout}>Kilépés</button>}
  </form>

  if (forced) return <div className="login-page">{form}</div>
  return <section><div className="page-head"><h1>Jelszó módosítása</h1></div><div className="panel password-change-panel">{form}</div></section>
}
